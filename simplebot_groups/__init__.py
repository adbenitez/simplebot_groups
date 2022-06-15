import io
import os
import queue
import time
from threading import Thread
from typing import Generator

import simplebot
from cairosvg import svg2png
from deltachat import Chat, Contact, Message
from deltachat.capi import lib
from deltachat.cutil import from_dc_charpointer
from simplebot.bot import DeltaBot, Replies

from .db import DBManager
from .templates import template

db: DBManager
channel_posts: queue.Queue = queue.Queue()


@simplebot.hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global db
    db = _get_db(bot)

    _getdefault(bot, "max_topic_size", "500")
    _getdefault(bot, "max_file_size", "1048576")

    prefix = _getdefault(bot, "command_prefix", "")

    allow_groups = _getdefault(bot, "allow_groups", "1")
    bot.commands.register(
        func=publish_cmd, name=f"/{prefix}publish", admin=(allow_groups != "1")
    )
    allow_channels = _getdefault(bot, "allow_channels", "1")
    bot.commands.register(
        func=chan_cmd, name=f"/{prefix}chan", admin=(allow_channels != "1")
    )
    bot.commands.register(func=remove_cmd, name=f"/{prefix}remove")
    bot.commands.register(func=topic_cmd, name=f"/{prefix}topic")
    bot.commands.register(func=adminchan_cmd, name=f"/{prefix}adminchan", admin=True)
    bot.commands.register(func=join_cmd, name=f"/{prefix}join")
    bot.commands.register(func=me_cmd, name=f"/{prefix}joined")
    bot.commands.register(func=list_cmd, name=f"/{prefix}list")
    bot.commands.register(func=info_cmd, name=f"/{prefix}info")

    desc = ""
    if allow_groups:
        desc = f"Add me to a group and send /{prefix}publish to make it public.\n"
    desc += f"Add me to a group and send /{prefix}info to get an invitation QR."
    bot.filters.register(func=filter_messages, help=desc)


@simplebot.hookimpl
def deltabot_start(bot: DeltaBot) -> None:
    Thread(target=_process_channels, args=(bot,), daemon=True).start()


@simplebot.hookimpl
def deltabot_member_removed(bot: DeltaBot, chat: Chat, contact: Contact) -> None:
    if bot.self_contact == contact or len(chat.get_contacts()) <= 1:
        if db.get_group(chat.id):
            db.remove_group(chat.id)
            return

        ch = db.get_channel(chat.id)
        if ch:
            if ch["admin"] == chat.id:
                for cchat in _get_cchats(bot, ch["id"]):
                    try:
                        cchat.remove_contact(bot.self_contact)
                    except ValueError:
                        pass
                db.remove_channel(ch["id"])
            else:
                db.remove_cchat(chat.id)


@simplebot.hookimpl
def deltabot_image_changed(deleted: bool, bot: DeltaBot, chat: Chat) -> None:
    ch = db.get_channel(chat.id)
    if ch and ch["admin"] == chat.id:
        for cchat in _get_cchats(bot, ch["id"]):
            try:
                if deleted:
                    cchat.delete_profile_image()
                else:
                    cchat.set_profile_image(chat.get_profile_image())
            except ValueError as ex:
                bot.logger.exception(ex)


@simplebot.hookimpl
def deltabot_ban(bot: DeltaBot, contact: Contact) -> None:
    me = bot.self_contact
    for g in db.get_groups():
        chat = bot.get_chat(g["id"])
        if chat:
            contacts = chat.get_contacts()
            if contact in contacts and me in contacts:
                chat.remove_contact(contact)

    for ch in db.get_channels():
        for chat in _get_cchats(bot, ch["id"]):
            contacts = chat.get_contacts()
            if contact in contacts and me in contacts:
                chat.remove_contact(contact)


def filter_messages(bot: DeltaBot, message: Message, replies: Replies) -> None:
    if not message.chat.is_group():
        return
    sender = message.get_sender_contact()
    if sender not in message.chat.get_contacts():
        return
    ch = db.get_channel(message.chat.id)
    if ch and ch["admin"] == message.chat.id:
        max_size = int(_getdefault(bot, "max_file_size"))
        if message.filename and os.path.getsize(message.filename) > max_size:
            replies.add(text=f"❌ File too big, up to {max_size} Bytes are allowed")
            return

        db.set_channel_last_pub(ch["id"], time.time())
        channel_posts.put((ch["name"], message, _get_cchats(bot, ch["id"])))
        replies.add(text="✔️Published", quote=message)
    elif ch:
        replies.add(text="❌ Only channel operators can do that.")


def publish_cmd(message: Message, replies: Replies) -> None:
    """Send this command in a group to make it public.

    To make your group private again just remove me from the group.
    """
    if not message.chat.is_group():
        replies.add(text="❌ This is not a group")
        return

    chan = db.get_channel(message.chat.id)
    if chan:
        replies.add(text="❌ This is a channel")
    else:
        group = db.get_group(message.chat.id)
        if group:
            replies.add(text="❌ This group is already public.")
        else:
            db.upsert_group(message.chat.id, None)
            replies.add(text="☑️ Group published")


def info_cmd(bot: DeltaBot, message: Message, replies: Replies) -> None:
    """Show the group/channel info."""
    chat = message.chat
    if not chat.is_group():
        replies.add(text="❌ This is not a group or channel")
        return

    prefix = _getdefault(bot, "command_prefix", "")

    ch = db.get_channel(chat.id)
    if ch:
        count = sum(
            map(lambda g: len(g.get_contacts()) - 1, _get_cchats(bot, ch["id"]))
        )
        replies.add(
            text=f"{ch['name']}\n👤 {count}\n{ch['topic'] or '-'}\n\n⬅️ /{prefix}remove_c{ch['id']}\n➡️ /{prefix}join_c{ch['id']}"
        )
        return

    group = db.get_group(chat.id)
    if group:
        count = len(chat.get_contacts())
        text = f"👤 {count}\n{group['topic'] or ''}\n\n⬅️ /{prefix}remove_g{group['id']}\n➡️ /{prefix}join_g{group['id']}"
    else:
        text = "Private group, share this QR to invite friends to join"

    svg = from_dc_charpointer(
        lib.dc_get_securejoin_qr_svg(bot.account._dc_context, chat.id)
    )
    png = io.BytesIO()
    svg2png(bytestring=svg, write_to=png)
    png.seek(0)
    replies.add(text=text, filename="img.png", bytefile=png)


def list_cmd(bot: DeltaBot, replies: Replies) -> None:
    """Show the list of public groups and channels."""

    def get_list(bot_addr: str, chats: list) -> str:
        return template.render(
            bot_addr=bot_addr,
            prefix=_getdefault(bot, "command_prefix", ""),
            chats=chats,
        )

    groups = []
    for g in db.get_groups():
        chat = bot.get_chat(g["id"])
        if not chat:
            db.remove_group(g["id"])
            continue
        groups.append(
            (
                chat.get_name(),
                g["topic"],
                f"g{chat.id}",
                None,
                len(chat.get_contacts()),
            )
        )
    total_groups = len(groups)
    if groups:
        groups.sort(key=lambda g: g[-1], reverse=True)
        text = f"⬇️ Groups ({total_groups}) ⬇️"
        replies.add(text=text, html=get_list(bot.self_contact.addr, groups))

    channels = []
    for ch in db.get_channels():
        count = sum(
            map(lambda g: len(g.get_contacts()) - 1, _get_cchats(bot, ch["id"]))
        )
        if ch["last_pub"]:
            last_pub = time.strftime("%d-%m-%Y", time.gmtime(ch["last_pub"]))
        else:
            last_pub = "-"
        channels.append(
            (
                ch["name"],
                ch["topic"],
                f"c{ch['id']}",
                last_pub,
                count,
            )
        )
    total_channels = len(channels)
    if channels:
        channels.sort(key=lambda g: g[-1], reverse=True)
        text = f"⬇️ Channels ({total_channels}) ⬇️"
        replies.add(text=text, html=get_list(bot.self_contact.addr, channels))

    if 0 == total_groups == total_channels:
        replies.add(text="❌ Empty List")


def me_cmd(bot: DeltaBot, message: Message, replies: Replies) -> None:
    """Show the list of groups and channels you are in."""
    sender = message.get_sender_contact()
    groups = []
    for group in db.get_groups():
        g = bot.get_chat(group["id"])
        contacts = g.get_contacts()
        if bot.self_contact not in contacts:
            db.remove_group(group["id"])
            continue
        if sender in contacts:
            groups.append((g.get_name(), f"g{g.id}"))

    for ch in db.get_channels():
        for c in _get_cchats(bot, ch["id"]):
            if sender in c.get_contacts():
                groups.append((ch["name"], f"c{ch['id']}"))
                break

    prefix = _getdefault(bot, "command_prefix", "")
    text = "{0}:\n⬅️ /{1}remove_{2}\n\n"
    replies.add(
        text="".join(text.format(name, prefix, id) for name, id in groups)
        or "Empty list"
    )


def join_cmd(bot: DeltaBot, args: list, message: Message, replies: Replies) -> None:
    """Join the given group/channel."""
    sender = message.get_sender_contact()
    prefix = _getdefault(bot, "command_prefix", "")
    arg = args[0] if args else ""
    if arg.startswith("g"):
        gid = int(arg[1:])
        gr = db.get_group(gid)
        if gr:
            g = bot.get_chat(gr["id"])
            contacts = g.get_contacts()
            if sender in contacts:
                replies.add(
                    text=f"❌ {sender.addr}, you are already a member of this group",
                    chat=g,
                )
            else:
                _add_contact(g, sender)
                replies.add(
                    chat=bot.get_chat(sender),
                    text=f"{g.get_name()}\n\n{gr['topic'] or '-'}\n\n⬅️ /{prefix}remove_{arg}",
                )
            return
    elif arg.startswith("c"):
        gid = int(arg[1:])
        ch = db.get_channel_by_id(gid)
        if ch:
            for g in _get_cchats(bot, ch["id"], include_admin=True):
                if sender in g.get_contacts():
                    replies.add(
                        text=f"❌ {sender.addr}, you are already a member of this channel",
                        chat=g,
                    )
                    return
            g = bot.create_group(ch["name"], [sender])
            db.add_cchat(g.id, ch["id"])
            img = bot.get_chat(ch["admin"]).get_profile_image()
            if img and os.path.exists(img):
                g.set_profile_image(img)
            replies.add(
                text=f"{ch['name']}\n\n{ch['topic'] or '-'}\n\n⬅️ /{prefix}remove_{arg}",
                chat=g,
            )
            return

    replies.add(text="❌ Invalid ID")


def adminchan_cmd(
    bot: DeltaBot, args: list, message: Message, replies: Replies
) -> None:
    """Join the admin group of the given channel."""
    ch = db.get_channel_by_id(int(args[0]))
    if ch:
        sender = message.get_sender_contact()
        _add_contact(bot.get_chat(ch["admin"]), sender)
        text = "{}\n\n{}".format(ch["name"], ch["topic"] or "")
        replies.add(text=text, chat=bot.get_chat(sender))
    else:
        replies.add(text="❌ Invalid ID")


def topic_cmd(bot: DeltaBot, payload: str, message: Message, replies: Replies) -> None:
    """Show or change group/channel topic."""
    if not message.chat.is_group():
        replies.add(text="❌ This is not a group")
        return

    if payload:
        max_size = int(_getdefault(bot, "max_topic_size"))
        if len(payload) > max_size:
            payload = payload[:max_size] + "..."

        text = f"** Topic changed to:\n{payload}"

        ch = db.get_channel(message.chat.id)
        if ch and ch["admin"] == message.chat.id:
            db.set_channel_topic(ch["id"], payload)
            for chat in _get_cchats(bot, ch["id"]):
                replies.add(text=text, chat=chat)
            replies.add(text=text)
            return
        if ch:
            replies.add(text="❌ Only channel operators can do that.")
            return

        g = db.get_group(message.chat.id)
        if not g:
            replies.add(text="❌ This group is not public")
            return
        db.upsert_group(g["id"], payload)
        replies.add(text=text)
        return

    g = db.get_channel(message.chat.id) or db.get_group(message.chat.id)
    if not g:
        replies.add(text="❌ This group is not public")
    else:
        replies.add(text=g["topic"] or "❌ No topic set", quote=message)


def remove_cmd(bot: DeltaBot, args: list, message: Message, replies: Replies) -> None:
    """Remove the member with the given address from the group with the given id. If no address is provided, removes yourself from group/channel."""
    sender = message.get_sender_contact()

    if not args:
        replies.add(text="❌ Invalid ID")
        return

    type_, gid = args[0][0], int(args[0][1:])
    if type_ == "c":
        ch = db.get_channel_by_id(gid)
        if not ch:
            replies.add(text="❌ Invalid ID")
            return
        for g in _get_cchats(bot, ch["id"], include_admin=True):
            if sender in g.get_contacts():
                g.remove_contact(sender)
                return
        replies.add(text="❌ You are not a member of that channel")
    elif type_ == "g":
        gr = db.get_group(gid)
        if not gr:
            replies.add(text="❌ Invalid ID")
            return
        g = bot.get_chat(gr["id"])
        if sender not in g.get_contacts():
            replies.add(text="❌ You are not a member of that group")
            return
        addr = args[-1] if "@" in args[-1] else ""
        if addr:
            if addr == bot.self_contact.addr:
                replies.add(text="❌ You can not remove me from the group")
                return
            contact = bot.get_contact(addr)
            g.remove_contact(contact)
            if not contact.is_blocked():
                chat = bot.get_chat(contact)
                replies.add(
                    text="❌ Removed from {} by {}".format(g.get_name(), sender.addr),
                    chat=chat,
                )
            replies.add(text="✔️{} removed".format(addr))
        else:
            g.remove_contact(sender)


def chan_cmd(bot: DeltaBot, payload: str, message: Message, replies: Replies) -> None:
    """Create a new channel with the given name."""
    if not payload:
        replies.add(text="❌ You must provide a channel name")
        return
    if db.get_channel_by_name(payload):
        replies.add(text="❌ There is already a channel with that name")
        return
    g = bot.create_group(payload, [message.get_sender_contact()])
    db.add_channel(payload, None, g.id)
    replies.add(text="✔️Channel created", chat=g)


def _getdefault(bot: DeltaBot, key: str, value: str = None) -> str:
    val = bot.get(key, scope=__name__)
    if val is None and value is not None:
        bot.set(key, value, scope=__name__)
        val = value
    return val


def _get_db(bot: DeltaBot) -> DBManager:
    path = os.path.join(os.path.dirname(bot.account.db_path), __name__)
    if not os.path.exists(path):
        os.makedirs(path)
    return DBManager(os.path.join(path, "sqlite.db"))


def _get_cchats(bot: DeltaBot, cgid: int, include_admin: bool = False) -> Generator:
    if include_admin:
        ch = db.get_channel_by_id(cgid)
        if ch:
            g = bot.get_chat(ch["admin"])
            if g:
                yield g
            else:
                db.remove_channel(cgid)
    for gid in db.get_cchats(cgid):
        g = bot.get_chat(gid)
        if g and bot.self_contact in g.get_contacts():
            yield g
        else:
            db.remove_cchat(gid)


def _add_contact(chat: Chat, contact: Contact) -> None:
    img_path = chat.get_profile_image()
    if img_path and not os.path.exists(img_path):
        chat.remove_profile_image()
    chat.add_contact(contact)


def _process_channels(bot: DeltaBot) -> None:
    while True:
        try:
            _send_diffusion(bot, *channel_posts.get())
        except Exception as ex:
            bot.logger.exception(ex)


def _send_diffusion(
    bot: DeltaBot, channel_name: str, message: Message, chats: list
) -> None:
    text = message.text
    html = message.html
    filename = message.filename
    quote = message.quote
    contact = message.get_sender_contact()
    sender = contact.name if contact.name != contact.addr else channel_name
    replies = Replies(message, logger=bot.logger)
    for chat in chats:
        replies.add(
            text=text,
            html=html,
            sender=sender,
            quote=quote,
            filename=filename,
            viewtype=message._view_type,
            chat=chat,
        )
    replies.send_reply_messages()
