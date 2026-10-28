from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser


class SafeJSONParser(JSONParser):
    """DRF answers bad JSON with a 400, but JSON nested deep enough to overflow
    the stack would still crash the request with a 500."""

    def parse(self, stream, media_type=None, parser_context=None):
        try:
            return super().parse(stream, media_type, parser_context)
        except RecursionError:
            raise ParseError("The JSON is nested too deeply.")
