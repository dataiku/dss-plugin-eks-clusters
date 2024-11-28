import logging
import os
import requests

def get_url_or_fallback(url, static_resource_filename):
    r = requests.get(url, headers={"User-Agent": "DSS EKS Plugin"})

    if url and r.ok:
        logging.debug("Successfully retrieved content from URL '%s'" % url)
        return r.text
    elif static_resource_filename:
        # Get the bundled static resource file as a fallback.
        logging.warning("Retrieving the file from URL '%s' failed with status: %s %s" % (url, r.status_code, r.reason))
        logging.warning("Content of failed request: %s" % r.content)
        logging.warning("Using bundled static resource '%s' as fallback." % static_resource_filename)
        return get_static_resource(static_resource_filename)
    else:
        logging.error("No static resource fallback was defined.")

def get_static_resource(static_resource_filename):
    static_resource_path = os.path.join(os.environ["DKU_CUSTOM_RESOURCE_FOLDER"], static_resource_filename)

    if os.path.exists(static_resource_path):
        logging.info("Found static resource at path: %s" % static_resource_path)
        with open(static_resource_path, "r") as f:
            resource_content_raw = f.read()
            return resource_content_raw
    else:
        logging.warning("Unable to locate the static resource at path: %s" % static_resource_path)