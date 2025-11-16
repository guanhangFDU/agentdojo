# src/agentdojo/my_suites/v1/slack/multi_round_suite.py
from collections.abc import Sequence
from agentdojo.task_suite.task_suite import TaskSuite
from agentdojo.functions_runtime import FunctionsRuntime, FunctionCall
from agentdojo.types import ChatMessage, MessageContentBlock
from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
from agentdojo.base_tasks import BaseUserTask, BaseInjectionTask
from agentdojo.agent_pipeline.errors import AbortAgentError
from agentdojo.task_suite.task_suite import (
    functions_stack_trace_from_messages,
    model_output_from_messages,
)
from agentdojo.my_suites.v1.slack.task_suite import SlackEnvironment

class MultiRoundSlackSuite(TaskSuite[SlackEnvironment]):
    def run_task_with_pipeline(
        self,
        agent_pipeline: BasePipelineElement,
        user_task: BaseUserTask[SlackEnvironment] | BaseInjectionTask[SlackEnvironment],
        injection_task: BaseInjectionTask[SlackEnvironment] | None,
        injections: dict[str, str],
        runtime_class: type[FunctionsRuntime] = FunctionsRuntime,
        environment: SlackEnvironment | None = None,
        verbose: bool = False,
    ) -> tuple[bool, bool]:
        if environment is None:
            environment = self.load_and_inject_default_environment(injections)

        if isinstance(user_task, BaseUserTask):
            task_env = user_task.init_environment(environment)
        else:
            task_env = environment

        pre_env = task_env.model_copy(deep=True)
        runtime = runtime_class(self.tools)
        messages: list[ChatMessage] = []

        # 获取分片提示
        prompts: list[str]
        if hasattr(user_task, "prompts"):
            prompts = user_task.prompts()  # [p1, p2, p3]
        elif hasattr(user_task, "prompt_for_round"):
            prompts = [user_task.prompt_for_round(i) for i in range(getattr(user_task, "ROUNDS", 1))]
        else:
            prompts = [user_task.PROMPT]

        round_utilities: list[bool] = []

        for i, prompt in enumerate(prompts):
            try:
                _, _, task_env, messages, _ = agent_pipeline.query(
                    prompt, runtime, task_env, messages=messages
                )
            except AbortAgentError as e:
                task_env = e.task_environment
                messages = e.messages

            model_output = model_output_from_messages(messages) or []
            traces: Sequence[FunctionCall] = functions_stack_trace_from_messages(messages)

            # 每轮评估：优先使用任务提供的 round 评估；否则沿用现有 utility/utility_from_traces
            if hasattr(user_task, "utility_round"):
                ok = user_task.utility_round(i, "".join([b["content"] or "" for b in model_output]), pre_env, task_env, traces)  # type: ignore
            else:
                out_text = "".join([b["content"] or "" for b in model_output])
                ok_from_traces = user_task.utility_from_traces(out_text, pre_env, task_env, traces)
                ok = ok_from_traces if ok_from_traces is not None else user_task.utility(out_text, pre_env, task_env)

            round_utilities.append(bool(ok))

        # 总体 utility：全部分片都通过才算通过
        utility = all(round_utilities)

        # 注入安全：按最终轮次判断（也可以扩展为逐轮判定并组合）
        if injection_task is None:
            return utility, True

        out_blocks: list[MessageContentBlock] = model_output_from_messages(messages) or []
        traces: Sequence[FunctionCall] = functions_stack_trace_from_messages(messages)
        out_text = "".join([b["content"] or "" for b in out_blocks])

        sec_from_traces = injection_task.security_from_traces(out_text, pre_env, task_env, traces)
        security = sec_from_traces if sec_from_traces is not None else injection_task.security(out_text, pre_env, task_env)

        return utility, security