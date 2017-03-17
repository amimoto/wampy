from wampy.messages.message import Message

class Authenticate(Message):
    """ When the server responds with a challenge and expects a response.

       [CHALLENGE, method, Details|dict]

    """
    WAMP_CODE = 5

    def __init__(self, signature, details_dict=None):
        self.signature = signature
        self.details = details_dict or {}

        self.message = [
            self.WAMP_CODE, self.signature, self.details,
        ]
