from wampy.messages.message import Message


class Challenge(Message):
    """ When the server responds with a challenge and expects a response.

       [CHALLENGE, method, Details|dict]

    """
    WAMP_CODE = 4

    def __init__(self, wamp_code, authmethod, details_dict):
        assert wamp_code == self.WAMP_CODE

        self.authmethod = authmethod
        self.details = details_dict

        self.message = [
            self.WAMP_CODE, self.authmethod, self.details,
        ]
