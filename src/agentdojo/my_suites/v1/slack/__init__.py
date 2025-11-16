from agentdojo.my_suites.v1.slack.injection_tasks import SlackInjectionTask  # noqa: F401 - Register tasks
from agentdojo.my_suites.v1.slack.task_suite import task_suite as my_slack_task_suite
from agentdojo.my_suites.v1.slack.user_tasks import SlackUserTask  # noqa: F401 - Register tasks

__all__ = ["my_slack_task_suite"]
