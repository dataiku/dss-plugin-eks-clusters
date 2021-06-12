def do(payload, config, plugin_config, inputs):
   choices = [
      { "value" : "val1", "label" : "Value 1"},
      { "value" : "val2", "label" : "Value 2"}
   ]
   return {"choices": choices}