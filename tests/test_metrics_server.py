import os
import sys
import unittest
from unittest import mock


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON_LIB = os.path.join(REPO_ROOT, "python-lib")
if PYTHON_LIB not in sys.path:
    sys.path.insert(0, PYTHON_LIB)

from dku_kube import metrics_server  # noqa: E402


class MetricsServerPresenceTest(unittest.TestCase):
    @mock.patch.object(metrics_server, "AwsCommand")
    def test_detects_metrics_server_managed_as_an_eks_addon(self, aws_command):
        aws_command.return_value.run.side_effect = [
            (["aws"], 0, "{}", ""),
            (["aws"], 254, "", "ResourceNotFoundException"),
        ]

        self.assertTrue(metrics_server.has_metrics_server_addon("cluster-id", {"region": "eu-west-1"}))
        self.assertFalse(metrics_server.has_metrics_server_addon("cluster-id", {"region": "eu-west-1"}))
        aws_command.assert_called_with(
            ["eks", "describe-addon", "--cluster-name", "cluster-id", "--addon-name", "metrics-server"],
            {"region": "eu-west-1"},
        )

    @mock.patch.object(metrics_server, "run_with_timeout")
    def test_detects_deployment_without_relying_on_pod_labels(self, run_with_timeout):
        run_with_timeout.return_value = ("deployment.apps/metrics-server\n", "")

        self.assertTrue(metrics_server.has_metrics_server("/tmp/kubeconfig"))
        cmd = run_with_timeout.call_args[0][0]
        self.assertEqual(
            ["kubectl", "get", "deployment", "metrics-server", "-n", "kube-system", "--ignore-not-found", "-o", "name"],
            cmd,
        )


if __name__ == "__main__":
    unittest.main()
