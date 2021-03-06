import pytest
from mock import ANY

from wampy.peers.clients import Client
from wampy.messages import Message
from wampy.roles.callee import register_rpc
from wampy.roles.subscriber import subscribe

from test.helpers import assert_stops_raising


class MetaClient(Client):

    def __init__(self, *args, **kwargs):
        super(MetaClient, self).__init__(*args, **kwargs)

        self.on_create_call_count = 0
        self.on_register_call_count = 0
        self.on_unregister_call_count = 0

    @subscribe(topic="wamp.registration.on_create")
    def on_create_handler(self, *args, **kwargs):
        """ Fired when a registration is created through a
        registration request for an URI which was
        previously without a registration. """
        self.on_create_call_count += 1

    @subscribe(topic="wamp.registration.on_register")
    def on_register_handler(self, *args, **kwargs):
        """ Fired when a Callee session is added to a
        registration. """
        self.on_register_call_count += 1

    @subscribe(topic="wamp.registration.on_unregister")
    def on_unregister_handler(self, *args, **kwargs):
        """Fired when a Callee session is removed from a
        registration. """
        self.on_unregister_call_count += 1


@pytest.yield_fixture
def meta_client(router):
    client = MetaClient(router=router)
    with client:
        yield client


class TestMetaEvents:

    def test_on_create(self, meta_client, router):

        class FooClient(Client):
            @register_rpc
            def foo(self):
                pass

        callee = FooClient(router=router)

        assert meta_client.on_create_call_count == 0

        with callee:
            def check_call_count():
                assert meta_client.on_create_call_count == 1

            assert_stops_raising(check_call_count)

    def test_on_register(self, meta_client, router):

        class FooClient(Client):
            @register_rpc
            def foo(self):
                pass

        callee = FooClient(router=router)
        caller = Client(router=router)

        with callee:
            with caller:
                caller.call("foo")

            def check_call_count():
                assert meta_client.on_register_call_count == 1

            assert_stops_raising(check_call_count)

    def test_on_unregister(self, meta_client, router):

        class FooClient(Client):
            @register_rpc
            def foo(self):
                pass

        callee = FooClient(router=router)

        assert meta_client.on_unregister_call_count == 0

        with callee:
            pass

        def check_call_count():
            assert meta_client.on_unregister_call_count == 1

        assert_stops_raising(check_call_count)


class TestMetaProcedures:

    def test_get_registration_list(self, router):
        client = Client(router=router)
        with client:
            registrations = client.get_registration_list()
            registered = registrations['exact']
            assert len(registered) == 0

            class DateService(Client):
                @register_rpc
                def get_date(self):
                    return "2016-01-01"

            service = DateService(router=router)
            with service:
                registrations = client.get_registration_list()
                registered = registrations['exact']
                assert len(registered) == 1

    def test_get_registration_lookup(self, router):
        client = Client(router=router)
        with client:
            registration_id = client.get_registration_lookup(
                procedure_name="spam")
            assert registration_id is None

            class SpamService(Client):
                @register_rpc
                def spam(self):
                    return "eggs and ham"

            service = SpamService(router=router)
            with service:
                registration_id = client.get_registration_lookup(
                    procedure_name="spam")
                assert registration_id in service.registration_map.values()
                assert len(service.registration_map.values()) == 1

    def test_registration_not_found(self, router):
        client = Client(router=router)
        with client:
            response_msg = client.get_registration(registration_id="spam")

            response_code, call_code, _, _, error_uri, args = (
                response_msg)

            assert response_code == Message.ERROR
            assert call_code == Message.CALL
            assert error_uri == u'wamp.error.no_such_registration'
            assert args == [
                u'no registration with ID spam exists on this dealer']

    def test_get_registration(self, router):
        class SpamService(Client):
            @register_rpc
            def spam(self):
                return "eggs and ham"

        service = SpamService(router=router)
        with service:
            registration_id = service.registration_map['spam']
            with Client(router=router) as client:
                info = client.get_registration(
                    registration_id=registration_id
                )

        expected_info = {
            'match': 'exact',
            'created': ANY,
            'uri': 'spam',
            'invoke': 'single',
            'id': registration_id,
        }

        assert expected_info == info

    def test_registration_match_not_found(self, router):
        client = Client(router=router)
        with client:
            matched_id = client.get_registration_match(
                procedure_name="spam")

            assert matched_id is None

    def test_get_registration_match(self, router):
        class SpamService(Client):
            @register_rpc
            def spam(self):
                return "eggs and ham"

        with SpamService(router=router) as service:
            with Client(router=router) as client:
                matched_id = client.get_registration_match(
                    procedure_name="spam")

                assert matched_id == service.registration_map['spam']

    def test_list_callees(self, router):
        class SpamService(Client):
            @register_rpc
            def spam(self):
                return "spam"

        class FooService(Client):
            @register_rpc
            def foo(self):
                return "foo"

        class BarService(Client):
            @register_rpc
            def bar(self):
                return "bar"

        with SpamService(router=router) as spam_service:
            registration_id = spam_service.registration_map['spam']

            # these are new sessions but not part of the same registration
            with FooService(router=router):
                with BarService(router=router):

                    with Client(router=router) as client:
                        callees = client.list_callees(registration_id)

                        assert len(callees) == 1
                        assert callees[0] == spam_service.session.id

    def test_count_callees(self, router):
        class SpamService(Client):
            @register_rpc
            def spam(self):
                return "spam"

        with SpamService(router=router) as spam_service:
            registration_id = spam_service.registration_map['spam']
            with Client(router=router) as client:
                count = client.count_callees(registration_id)
                assert count == 1
