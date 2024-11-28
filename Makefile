plugin_id=`cat plugin.json | python -c "import sys, json; print(str(json.load(sys.stdin)['id']).replace('/',''))"`
plugin_version=`cat plugin.json | python -c "import sys, json; print(str(json.load(sys.stdin)['version']).replace('/',''))"`
archive_file_name="dss-plugin-${plugin_id}-${plugin_version}.zip"
remote_url=`git config --get remote.origin.url`
last_commit_id=`git rev-parse HEAD`

plugin:
	@echo "[START] Archiving plugin to dist/ folder..."
	@cat plugin.json | json_pp > /dev/null
	@rm -rf dist
	@mkdir -p resource
	@wget https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/main/deployments/static/nvidia-device-plugin.yml -P resource
	@wget https://raw.githubusercontent.com/kubernetes-sigs/aws-alb-ingress-controller/v1.1.4/docs/examples/alb-ingress-controller.yaml -P resource
	@wget https://raw.githubusercontent.com/kubernetes-sigs/aws-alb-ingress-controller/v1.1.8/docs/examples/iam-policy.json -P resource
	@mkdir dist
	@echo "{\"remote_url\":\"${remote_url}\",\"last_commit_id\":\"${last_commit_id}\"}" > release_info.json
	@git archive -v -9 --format zip -o dist/${archive_file_name} HEAD
	@zip -u dist/${archive_file_name} release_info.json
	@zip -u dist/${archive_file_name} resource/nvidia-device-plugin.yml
	@zip -u dist/${archive_file_name} resource/alb-ingress-controller.yaml
	@zip -u dist/${archive_file_name} resource/iam-policy.json
	@rm release_info.json
	@rm resource/nvidia-device-plugin.yml
	@rm resource/alb-ingress-controller.yaml
	@rm resource/iam-policy.json
	@echo "[SUCCESS] Archiving plugin to dist/ folder: Done!"

dist-clean:
	rm -rf dist