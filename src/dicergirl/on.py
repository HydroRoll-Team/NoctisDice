from nonebot.plugin import on_message, on_startswith
from nonebot.rule import Rule
from nonebot.adapters import Event, Bot
from nonebot.matcher import Matcher
from infini.input import Input
from infini.injector import Injector
from diceutils.utils import format_msg
from diceutils.parser import CommandParser, Commands, Optional, Bool
from diceutils.status import StatusPool

from .utils import hmr, get_core
from .workflow import put, workflows
import json


class Interceptor:
    __slots__ = ("msg", "ignorecase")

    def __init__(self, msg: str = "", ignorecase: bool = False):
        self.msg = msg
        self.ignorecase = ignorecase

    def __repr__(self) -> str:
        return f"Interceptor(msg={self.msg}, ignorecase={self.ignorecase})"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Interceptor)
            and frozenset(self.msg) == frozenset(other.msg)
            and self.ignorecase == other.ignorecase
        )

    def __hash__(self) -> int:
        return hash((frozenset(self.msg), self.ignorecase))

    async def __call__(self) -> bool:
        return True


injector = Injector()
interceptor = on_message(Rule(Interceptor()), priority=1, block=True)
ipm = on_startswith(".ipm", priority=0, block=True)

hmr()


@ipm.handle()
async def ipm_handler(event: Event, matcher: Matcher):
    args = format_msg(event.get_plaintext(), begin=".ipm")
    commands = CommandParser(
        Commands(
            [
                Bool("hmr"),
                Optional("add", str),
                Optional("remove", str),
                Bool("clear"),
                Bool("show"),
            ]
        ),
        args=args,
        auto=True,
    ).results

    status = StatusPool.get("dicergirl")

    if commands["hmr"]:
        hmr()
        return await matcher.send("Infini 热重载完毕")

    if commands["add"]:
        packages = status.get("bot", "packages") or []
        packages.append(commands["add"])
        status.set("bot", "packages", packages)
        hmr()
        return await matcher.send(f"规则包[{commands['add']}]挂载完成")

    if commands["clear"]:
        status.set("bot", "packages", [])
        hmr()
        return await matcher.send(f"挂载规则包已清空")

    if commands["show"]:
        packages = status.get("bot", "packages") or []
        return await matcher.send(f"挂载规则包: {[package for package in packages]!r}")

    if commands["remove"]:
        packages = status.get("bot", "packages") or []
        if commands["remove"] in packages:
            packages.remove(commands["remove"])
            status.set("bot", "packages", packages)
            return await matcher.send(f"规则包[{commands['remove']}]卸载完成")
        return await matcher.send(f"规则包[{commands['remove']}]未挂载")

    await matcher.send(
        "Infini Package Manager 版本 1.0.0-beta.1 [IPM for Infini v2.0.6]\n"
        "欢迎使用 IPM, 使用`.help ipm`查看 IPM 使用帮助."
    )


@interceptor.handle()
async def handler(bot: Bot, event: Event, matcher: Matcher):
    nb_event_name = event.get_event_name()
    nb_event_type = event.get_type()
    nb_event_description = event.get_event_description()
    nb_event_json: dict = json.loads(event.json())

    nickname = (nb_event_json.get("user", {})).get("nickname") or (
        nb_event_json.get("sender", {})
    ).get("nickname")
    user_id = str(event.get_user_id())
    self_id = str(nb_event_json.get("self_id"))
    group_id = str(event.group_id) if hasattr(event, "group_id") else None
    session_id = event.get_session_id()

    plain_text = event.get_plaintext()
    message = [{"type": msg.type, "data": msg.data} for msg in event.get_message()]
    mentions = [
        mention["data"]["qq"]
        for mention in nb_event_json["original_message"]
        if mention["type"] == "at"
    ]
    is_tome = False

    if self_id in mentions:
        is_tome = True
    elif not mentions:
        is_tome = True
    else:
        if mentions:
            if nb_event_json["original_message"][0]["type"] != "at":
                is_tome = True

    input = Input(
        plain_text,
        variables={
            "nickname": nickname,
            "user_id": user_id,
            "self_id": self_id,
            "group_id": group_id,
            "session_id": session_id,
            "message": message,
            "mentions": mentions,
            "is_tome": is_tome,
            "nb_event_name": nb_event_name,
            "nb_event_type": nb_event_type,
            "nb_event_description": nb_event_description,
            "nb_event_json": nb_event_json,
            "platform": "Nonebot2",
        },
    )

    for output in get_core().input(input):
        if isinstance(output, str):
            await matcher.send(output)
        else:
            parameters = {"output": output, "bot": bot, "matcher": matcher}
            parameters.update(output.variables)
            put(injector.inject(workflows.get(output.name), parameters=parameters))
