import os
import sys
import types
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON_LIB = os.path.join(REPO_ROOT, "python-lib")
if PYTHON_LIB not in sys.path:
    sys.path.insert(0, PYTHON_LIB)


class FakeRegistry(object):
    def __init__(self):
        self.tags = []
        self.containers = []
        self.error = None

    def get_tags(self, container, N=None):
        self.containers.append(container)
        if self.error is not None:
            raise self.error
        return list(self.tags)


sys.modules.setdefault("yaml", types.SimpleNamespace())
sys.modules.setdefault("six", types.SimpleNamespace(text_type=str))
sys.modules.setdefault("requests", types.SimpleNamespace(RequestException=Exception))
sys.modules.setdefault("oras", types.SimpleNamespace())
sys.modules["oras.provider"] = types.SimpleNamespace(Registry=FakeRegistry)

from dku_kube import autoscaler  # noqa: E402


class AutoscalerImageSelectionTest(unittest.TestCase):
    def setUp(self):
        autoscaler.k8s_image_client = FakeRegistry()

    def test_parse_autoscaler_tag_accepts_only_full_patch_versions(self):
        self.assertEqual((1, 35, 0), autoscaler._parse_autoscaler_tag("v1.35.0"))
        self.assertEqual((12, 3, 456), autoscaler._parse_autoscaler_tag("v12.3.456"))

        self.assertIsNone(autoscaler._parse_autoscaler_tag("latest"))
        self.assertIsNone(autoscaler._parse_autoscaler_tag("v1.35"))
        self.assertIsNone(autoscaler._parse_autoscaler_tag("1.35.0"))
        self.assertIsNone(autoscaler._parse_autoscaler_tag("dss-qa-1_35"))

    def test_discover_published_autoscaler_tags_filters_non_version_tags(self):
        autoscaler.k8s_image_client.tags = ["latest", "v1.35", "v1.34.3", "v1.35.0", "dss-qa-1_35"]

        self.assertEqual(["v1.34.3", "v1.35.0"], autoscaler._discover_published_autoscaler_tags("registry.k8s.io"))
        self.assertEqual(["registry.k8s.io/autoscaling/cluster-autoscaler"], autoscaler.k8s_image_client.containers)

    def test_discover_published_autoscaler_tags_keeps_registry_namespace_prefix(self):
        autoscaler.k8s_image_client.tags = ["v1.35.0"]

        self.assertEqual(
            ["v1.35.0"],
            autoscaler._discover_published_autoscaler_tags("123456789012.dkr.ecr.eu-west-1.amazonaws.com/valrutz"),
        )
        self.assertEqual(
            ["123456789012.dkr.ecr.eu-west-1.amazonaws.com/valrutz/autoscaling/cluster-autoscaler"],
            autoscaler.k8s_image_client.containers,
        )

    def test_select_matching_autoscaler_tag_from_tags_uses_latest_patch_for_minor(self):
        tags = ["v1.35.0", "v1.33.4", "v1.35.2", "v1.35.1", "not-a-version"]

        self.assertEqual("v1.35.2", autoscaler._select_matching_autoscaler_tag_from_tags(tags, (1, 35)))
        self.assertEqual("v1.33.4", autoscaler._select_matching_autoscaler_tag_from_tags(tags, (1, 33)))
        self.assertIsNone(autoscaler._select_matching_autoscaler_tag_from_tags(tags, (1, 36)))

    def test_select_autoscaler_image_uses_override_without_discovery(self):
        autoscaler.k8s_image_client.error = ValueError("discovery should not be called")

        selected_tag = autoscaler.select_autoscaler_image("1.35", "registry.k8s.io", "dss-qa-1_35")

        self.assertEqual("dss-qa-1_35", selected_tag)
        self.assertEqual([], autoscaler.k8s_image_client.containers)

    def test_select_autoscaler_image_uses_matching_published_tag(self):
        autoscaler.k8s_image_client.tags = ["v1.33.3", "v1.35.0", "v1.33.4"]

        self.assertEqual("v1.33.4", autoscaler.select_autoscaler_image("1.33", "registry.k8s.io"))

    def test_select_autoscaler_image_accepts_kubernetes_patch_version(self):
        autoscaler.k8s_image_client.tags = ["v1.35.0", "v1.35.1"]

        self.assertEqual("v1.35.1", autoscaler.select_autoscaler_image("1.35.7", "registry.k8s.io"))

    def test_select_autoscaler_image_falls_back_to_bundled_matching_tag_when_discovery_fails(self):
        autoscaler.k8s_image_client.error = ValueError("tags/list unavailable")

        self.assertEqual("v1.33.4", autoscaler.select_autoscaler_image("1.33", "private.example"))

    def test_select_autoscaler_image_uses_latest_bundled_tag_when_discovery_fails_and_no_fallback_matches(self):
        autoscaler.k8s_image_client.error = ValueError("tags/list unavailable")

        self.assertEqual("v1.35.0", autoscaler.select_autoscaler_image("1.36", "private.example"))

    def test_select_autoscaler_image_falls_back_to_bundled_matching_tag_when_published_match_missing(self):
        autoscaler.k8s_image_client.tags = ["v1.35.0"]

        self.assertEqual("v1.33.4", autoscaler.select_autoscaler_image("1.33", "registry.k8s.io"))

    def test_select_autoscaler_image_uses_latest_bundled_tag_when_no_matching_fallback_exists(self):
        autoscaler.k8s_image_client.tags = ["v1.35.0"]

        self.assertEqual("v1.35.0", autoscaler.select_autoscaler_image("1.36", "registry.k8s.io"))

    def test_get_autoscaler_config_uses_selected_registry_and_tag(self):
        config = autoscaler.get_autoscaler_config("cluster-1", "v1.35.0", "registry.example.com/prefix/", "eu-west-1")

        self.assertIn("image: registry.example.com/prefix/autoscaling/cluster-autoscaler:v1.35.0", config)
        self.assertIn("k8s.io/cluster-autoscaler/cluster-1", config)
        self.assertIn("name: AWS_REGION\n              value: eu-west-1", config)

    def test_failure_on_purpose(self):
        with self.assertRaises(ValueError):
            autoscaler.select_autoscaler_image("1.33", "registry.k8s.io", "nonexistent-tag")


if __name__ == "__main__":
    unittest.main()
