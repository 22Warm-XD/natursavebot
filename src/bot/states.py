from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class LoginStates(StatesGroup):
    api_id = State()
    api_hash = State()
    phone = State()
    code = State()
    password = State()


class DraftStates(StatesGroup):
    editing = State()
