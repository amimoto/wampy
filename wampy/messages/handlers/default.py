import logging

from wampy.messages import MESSAGE_TYPE_MAP
from wampy.messages import (
    Goodbye, Error, Event, Invocation, Registered, Result, Subscribed,
    Welcome, Yield, Challenge)
from wampy.errors import WampyError

logger = logging.getLogger('wampy.messagehandler')


class MessageHandler(object):

    def __init__(
        self, client, session, message_queue, messages_to_handle=None,
    ):
        """ Responsible for processing incoming WAMP messages.

        :Parameters:
            client : instance of `wampy.peers.clients.Client`
                The wampy client receiving the messages.

            messages_to_handle : list
                A list of Message classes. Only Messages described in
                this list will be accepted.

        """
        self.client = client
        self.session = session
        self.message_queue = message_queue

        if messages_to_handle is None:
            # the rationale here is as follows:-
            # Welcome: mandatory for Session establishment
            # Challenge: used for authentication
            # Goodbye: mandatory because GOODBYE is echoed by the Router
            # Registered: a client is likely to be a Callee
            # Invocation: same as above
            # Yield: and again
            # Result: a client is likely to be a Caller
            # Error: for debugging clients
            # Subscribed: because a client is likely to be a Subscriber
            # Event: sames as above
            self.messages_to_handle = [
                Welcome, Challenge, Goodbye, Registered, Invocation, Yield, Result,
                Error, Subscribed, Event
            ]
        else:
            for message in messages_to_handle:
                # validation here
                pass

            self.messages_to_handle = messages_to_handle

        self.messages = {}
        self._configure_messages()

    def __call__(self, *args, **kwargs):
        return self.handle_message(*args, **kwargs)

    def _configure_messages(self):
        messages = self.messages
        for message in self.messages_to_handle:
            messages[message.WAMP_CODE] = message

    def handle_message(self, message):
        wamp_code = message[0]
        if wamp_code not in self.messages:
            raise WampyError(
                "No message handler is configured for: {}".format(
                    MESSAGE_TYPE_MAP[wamp_code])
            )

        logger.info(
            "received message: %s", MESSAGE_TYPE_MAP[wamp_code]
        )

        message_class = self.messages[wamp_code]
        message_obj = message_class(*message)
        message_obj.process(message=message, client=self.client)

        self.message_queue.put(message)
