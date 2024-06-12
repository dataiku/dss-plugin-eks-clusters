# Changelog

## Version 1.4.2 - Bugfix release
- Fix clusters creation with GPU driver with Python 2 code environments

## Version 1.4.1 - Bugfix release
- Fix an issue when using the action to add a node pool with GPU

## Version 1.4.0 - Feature and bugfix release
- Allowing for multiple node pool definitions on cluster startup
- Adding labels and taints support for node pools
- Ensure latest version of Nvidia driver for GPU

## Version 1.3.2 - Bugfix release
- Update Nvidia driver URL to new location

## Version 1.3.1 - Bugfix release
- Fix a bug where node pool configuration is ignored

## Version 1.2.3 - Feature and bugfix release
- Choose autoscaler version based on the Kubernetes cluster version. For Kubernetes prior to 1.24, autoscaler version used is `v1.24.3`
- Increase default disk size for the nodes to 200GB

## Version 1.2.2 - Bugfix release
- Make plugin compatible with AWS requiring IMDS_V2 instances

## Version 1.2.1 - Bugfix release
- Added `wait` option to "resize cluster" macro
- Support non-numeric-only `kubectl` versions

## Version 1.2.0 - Internal release
- Added support for Python 3.8, 3.9, 3.10 (experimental), 3.11 (experimental)
- Python 2.7 is now deprecated
- Macro `Add node pool` now adds the node pool in the cluster security groups

## Version 1.1.1 - Bugfix release
- Add support of v1beta1 apiVersion when attaching

## Version 1.1.0 - Feature release
- Add support for fully-managed private clusters

## Version 1.0.9 - Bugfix release
- Throwing an exception when command invoked by `EksctlCommand.run_and_get_output` or `AwsCommand.run_and_get_output` fails
- Handle creating fully-private clusters (nodes in private subnets and private control plane endpoint)

## Version 1.0.8 - Feature and bugfix release
- Add option to install Metrics Server
- Fix "Inspect node pools" macro when using managed node groups
- Support tagging nodes
- Remove macro `Run Kubectl command` (natively supported in DSS 10.0.6)
- Support spot instances in node groups
- Update autoscaler to v1.20.2

## Version 1.0.7 - Bugfix release
- Add capability to assume IAM role on all cluster operation
- Fix use of `AWS_DEFAULT_REGION` environment variable

## Version 1.0.6 - Bugfix release
- Trim security group parameter string
- Update eksctl download URL
- Fix several Python 3 related issues

## Version 1.0.5 - Internal release
- Add support for Python 3

## Version 1.0.4 - Internal release
- Add GPU Driver support

## Version 1.0.3 - Bugfix release
- Fix the "resize cluster" macro

## Version 1.0.2 - Bugfix release
- Fix `Test network connectivity` macro when the hostname is already an IP.
