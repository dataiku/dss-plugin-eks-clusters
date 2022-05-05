# Changelog

## Next version
- Fix "Inspect node pools" macro when using managed node groups
- Remove macro `Run Kubectl command` (natively supported in DSS 10.0.6)

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
