"""Web search confirmation resolved per user through group permissions.

Run inside the Open WebUI image (the module imports the app configuration):
    python -m unittest open_webui.test.test_web_search_confirmation
"""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from open_webui.config import DEFAULT_USER_PERMISSIONS
from open_webui.routers.users import FeaturesPermissions
from open_webui.utils.access_control import get_permissions, requires_web_search_confirmation

PERMISSION = 'web_search_without_confirmation'
USER = SimpleNamespace(id='user-1', role='user')
ADMIN = SimpleNamespace(id='admin-1', role='admin')


def group(**features):
    return SimpleNamespace(permissions={'features': features})


class WebSearchConfirmationTests(unittest.IsolatedAsyncioTestCase):
    async def required(self, user, groups=(), enabled=True, defaults=None):
        with patch(
            'open_webui.utils.access_control.Groups.get_groups_by_member_id',
            new=AsyncMock(return_value=list(groups)),
        ):
            return await requires_web_search_confirmation(user, enabled, defaults)

    def test_the_permission_is_off_by_default(self):
        self.assertIs(False, DEFAULT_USER_PERMISSIONS['features'][PERMISSION])
        self.assertIs(False, FeaturesPermissions().web_search_without_confirmation)

    def test_the_admin_form_keeps_the_permission(self):
        saved = FeaturesPermissions(**{PERMISSION: True}).model_dump()
        self.assertIs(True, saved[PERMISSION])

    async def test_a_user_without_the_permission_confirms(self):
        self.assertTrue(await self.required(USER))
        # Groups saved before the permission existed, or that only grant web search itself.
        self.assertTrue(await self.required(USER, [group(web_search=True), SimpleNamespace(permissions=None)]))
        self.assertTrue(await self.required(USER, [group(**{PERMISSION: False})]))

    async def test_a_group_lifts_the_confirmation_for_its_members(self):
        self.assertFalse(await self.required(USER, [group(**{PERMISSION: True})]))

    async def test_the_most_permissive_group_wins(self):
        groups = [group(**{PERMISSION: False}), group(**{PERMISSION: True})]
        self.assertFalse(await self.required(USER, groups))

    async def test_the_default_permissions_can_lift_it_for_everyone(self):
        self.assertFalse(await self.required(USER, defaults={'features': {PERMISSION: True}}))
        self.assertTrue(await self.required(USER, defaults={'features': {'web_search': True}}))

    async def test_admins_are_exempt_like_for_other_feature_permissions(self):
        self.assertFalse(await self.required(ADMIN))

    async def test_nobody_confirms_when_the_admin_setting_is_off(self):
        self.assertFalse(await self.required(USER, enabled=False))
        self.assertFalse(await self.required(ADMIN, enabled=False))
        self.assertFalse(await self.required(USER, enabled=None))

    async def test_an_unknown_caller_keeps_the_admin_setting(self):
        self.assertTrue(await self.required(None))
        self.assertFalse(await self.required(None, enabled=False))

    async def test_the_users_permission_list_carries_it(self):
        with patch(
            'open_webui.utils.access_control.Groups.get_groups_by_member_id',
            new=AsyncMock(return_value=[group(web_search=True), group(**{PERMISSION: True})]),
        ):
            permissions = await get_permissions('user-1', {'features': {'web_search': True}})
        self.assertIs(True, permissions['features'][PERMISSION])
        with patch(
            'open_webui.utils.access_control.Groups.get_groups_by_member_id', new=AsyncMock(return_value=[])
        ):
            permissions = await get_permissions('user-1', {'features': {'web_search': True}})
        self.assertIs(False, permissions['features'][PERMISSION])
