def env_get(Variable):
	import os
	import json
	return str(os.getenv(Variable))