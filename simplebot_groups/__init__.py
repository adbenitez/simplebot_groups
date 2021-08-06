import io
import os
import queue
import time
from threading import Thread
from typing import Generator

import qrcode
import simplebot
from deltachat import Chat, Contact, Message
from jinja2 import Template
from simplebot.bot import DeltaBot, Replies

from .db import DBManager

__version__ = "1.0.0"
db: DBManager
channel_posts: queue.Queue = queue.Queue()


@simplebot.hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global db
    db = _get_db(bot)

    _getdefault(bot, "max_group_size", "999999")
    _getdefault(bot, "max_topic_size", "500")
    _getdefault(bot, "allow_groups", "1")
    _getdefault(bot, "max_file_size", "504800")
    allow_channels = _getdefault(bot, "allow_channels", "1")

    bot.commands.register(
        func=cmd_chan, name="/group_chan", admin=(allow_channels != "1")
    )


@simplebot.hookimpl
def deltabot_start(bot: DeltaBot) -> None:
    Thread(target=_process_channels, args=(bot,), daemon=True).start()


@simplebot.hookimpl
def deltabot_member_added(
    bot: DeltaBot, chat: Chat, contact: Contact, actor: Contact
) -> None:
    if contact == bot.self_contact and not db.get_channel(chat.id):
        _add_group(bot, chat.id, as_admin=bot.is_admin(actor.addr))


@simplebot.hookimpl
def deltabot_member_removed(bot: DeltaBot, chat: Chat, contact: Contact) -> None:
    me = bot.self_contact
    if me == contact or len(chat.get_contacts()) <= 1:
        g = db.get_group(chat.id)
        if g:
            db.remove_group(chat.id)
            return

        ch = db.get_channel(chat.id)
        if ch:
            if ch["admin"] == chat.id:
                for cchat in _get_cchats(bot, ch["id"]):
                    try:
                        cchat.remove_contact(me)
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


@simplebot.filter(name=__name__)
def filter_messages(bot: DeltaBot, message: Message, replies: Replies) -> None:
    """Process messages sent to channels."""
    ch = db.get_channel(message.chat.id)
    if ch and ch["admin"] == message.chat.id:
        if message.get_sender_contact() not in message.chat.get_contacts():
            return
        max_size = int(_getdefault(bot, "max_file_size"))
        if message.filename and os.path.getsize(message.filename) > max_size:
            replies.add(
                text="❌ File too big, up to {} Bytes are allowed".format(max_size)
            )
            return

        db.set_channel_last_pub(ch["id"], time.time())
        channel_posts.put((message, _get_cchats(bot, ch["id"])))
        replies.add(text="✔️Published", quote=message)
    elif ch:
        replies.add(text="❌ Only channel operators can do that.")


@simplebot.command
def group_info(bot: DeltaBot, message: Message, replies: Replies) -> None:
    """Show the group/channel info."""
    if not message.chat.is_group():
        replies.add(text="❌ This is not a group")
        return

    text = "{0}\n👤 {1}\n{2}\n\n"
    text += "⬅️ /group_remove_{3}{4}\n➡️ /group_join_{3}{4}"

    ch = db.get_channel(message.chat.id)
    if ch:
        count = sum(
            map(lambda g: len(g.get_contacts()) - 1, _get_cchats(bot, ch["id"]))
        )
        replies.add(
            text=text.format(ch["name"], count, ch["topic"] or "-", "c", ch["id"])
        )
        return

    g = db.get_group(message.chat.id)
    if not g:
        addr = message.get_sender_contact().addr
        _add_group(bot, message.chat.id, as_admin=bot.is_admin(addr))
        g = db.get_group(message.chat.id)
        assert g is not None

    chat = bot.get_chat(g["id"])
    img = qrcode.make(chat.get_join_qr())
    buffer = io.BytesIO()
    img.save(buffer, format="jpeg")
    buffer.seek(0)
    count = len(bot.get_chat(g["id"]).get_contacts())
    replies.add(
        text=text.format(chat.get_name(), count, g["topic"] or "-", "g", g["id"]),
        filename="img.jpg",
        bytefile=buffer,
    )


@simplebot.command
def group_list(bot: DeltaBot, replies: Replies) -> None:
    """Show the list of public groups and channels."""

    def get_list(chats):
        return Template(
            """
<style>
.w3-card-2{box-shadow:0 2px 4px 0 rgba(0,0,0,0.16),0 2px 10px 0 rgba(0,0,0,0.12) !important; margin-bottom: 15px;}
.w3-btn{border:none;display:inline-block;outline:0;padding:6px 16px;vertical-align:middle;overflow:hidden;text-decoration:none !important;color:#fff;background-color:#5a6f78;text-align:center;cursor:pointer;white-space:nowrap}
.w3-container:after,.w3-container:before{content:"";display:table;clear:both}
.w3-container{padding:0.01em 16px}
.w3-right{float:right !important}
.w3-large{font-size:18px !important}
.w3-delta,.w3-hover-delta:hover{color:#fff !important;background-color:#5a6f78 !important}
</style>
{% for name, topic, gid, last_pub, bot_addr, count in chats %}
<div class="w3-card-2">
<header class="w3-container w3-delta">
<h2>{{ name }}</h2>
</header>
<div class="w3-container">
<p>👤 {{ count }}</p>
{% if last_pub %}
📝 {{ last_pub }}
{% endif %}
<p>{{ topic }}</p>
</div>
<a class="w3-btn w3-large" href="mailto:{{ bot_addr }}?body=/group_remove_{{ gid }}">« Leave</a>
<a class="w3-btn w3-large w3-right" href="mailto:{{ bot_addr }}?body=/group_join_{{ gid }}">Join »</a>
</div>
{% endfor %}
"""
        ).render(chats=chats)

    groups = []
    for g in db.get_groups():
        chat = bot.get_chat(g["id"])
        if not chat:
            db.remove_group(g["id"])
            continue
        groups.append(
            (
                chat.get_name(),
                g["topic"] or "-",
                "g{}".format(chat.id),
                None,
                bot.self_contact.addr,
                len(chat.get_contacts()),
            )
        )
    total_groups = len(groups)
    if groups:
        groups.sort(key=lambda g: g[-1], reverse=True)
        text = "⬇️ Groups ({}) ⬇️".format(total_groups)
        replies.add(text=text, html=get_list(groups))

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
                ch["topic"] or "-",
                "c{}".format(ch["id"]),
                last_pub,
                bot.self_contact.addr,
                count,
            )
        )
    total_channels = len(channels)
    if channels:
        channels.sort(key=lambda g: g[-1], reverse=True)
        text = "⬇️ Channels ({}) ⬇️".format(total_channels)
        replies.add(text=text, html=get_list(channels))

    if 0 == total_groups == total_channels:
        replies.add(text="❌ Empty List")


@simplebot.command
def group_me(bot: DeltaBot, message: Message, replies: Replies) -> None:
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
            groups.append((g.get_name(), "g{}".format(g.id)))

    for ch in db.get_channels():
        for c in _get_cchats(bot, ch["id"]):
            if sender in c.get_contacts():
                groups.append((ch["name"], "c{}".format(ch["id"])))
                break

    text = "{0}:\n⬅️ /group_remove_{1}\n\n"
    replies.add(text="".join(text.format(*g) for g in groups) or "Empty list")


@simplebot.command
def group_join(bot: DeltaBot, args: list, message: Message, replies: Replies) -> None:
    """Join the given group/channel."""
    sender = message.get_sender_contact()
    is_admin = bot.is_admin(sender.addr)
    text = "{}\n\n{}\n\n⬅️ /group_remove_{}"
    arg = args[0] if args else ""
    if arg.startswith("g"):
        gid = int(arg[1:])
        gr = db.get_group(gid)
        if gr:
            g = bot.get_chat(gr["id"])
            contacts = g.get_contacts()
            if sender in contacts:
                replies.add(
                    text="❌ {}, you are already a member of this group".format(
                        sender.addr
                    ),
                    chat=g,
                )
            elif len(contacts) < int(_getdefault(bot, "max_group_size")) or is_admin:
                _add_contact(g, sender)
                replies.add(
                    chat=bot.get_chat(sender),
                    text=text.format(g.get_name(), gr["topic"] or "-", arg),
                )
            else:
                replies.add(text="❌ Group is full")
            return
    elif arg.startswith("c"):
        gid = int(arg[1:])
        ch = db.get_channel_by_id(gid)
        if ch:
            for g in _get_cchats(bot, ch["id"], include_admin=True):
                if sender in g.get_contacts():
                    replies.add(
                        text="❌ {}, you are already a member of this channel".format(
                            sender.addr
                        ),
                        chat=g,
                    )
                    return
            g = bot.create_group(ch["name"], [sender])
            db.add_cchat(g.id, ch["id"])
            img = bot.get_chat(ch["id"]).get_profile_image()
            if img and os.path.exists(img):
                g.set_profile_image(img)
            replies.add(text=text.format(ch["name"], ch["topic"] or "-", arg), chat=g)
            return

    replies.add(text="❌ Invalid ID")


@simplebot.command(admin=True)
def group_adminchan(
    bot: DeltaBot, args: list, message: Message, replies: Replies
) -> None:
    """Join the admin group of the given channel."""
    ch = db.get_channel_by_id(int(args[0]))
    if ch:
        sender = message.get_sender_contact()
        _add_contact(bot.get_chat(ch["admin"]), sender)
        text = "{}\n\n{}".format(ch["name"], ch["topic"] or "-")
        replies.add(text=text, chat=bot.get_chat(sender))
    else:
        replies.add(text="❌ Invalid ID")


@simplebot.command
def group_topic(bot: DeltaBot, args: list, message: Message, replies: Replies) -> None:
    """Show or change group/channel topic."""
    if not message.chat.is_group():
        replies.add(text="❌ This is not a group")
        return

    if args:
        new_topic = " ".join(args)
        max_size = int(_getdefault(bot, "max_topic_size"))
        if len(new_topic) > max_size:
            new_topic = new_topic[:max_size] + "..."

        text = "** {} changed topic to:\n{}"

        ch = db.get_channel(message.chat.id)
        if ch and ch["admin"] == message.chat.id:
            name = _get_name(message.get_sender_contact())
            text = text.format(name, new_topic)
            db.set_channel_topic(ch["id"], new_topic)
            for chat in _get_cchats(bot, ch["id"]):
                replies.add(text=text, chat=chat)
            replies.add(text=text)
            return
        if ch:
            replies.add(text="❌ Only channel operators can do that.")
            return

        addr = message.get_sender_contact().addr
        g = db.get_group(message.chat.id)
        if not g:
            _add_group(bot, message.chat.id, as_admin=bot.is_admin(addr))
            g = db.get_group(message.chat.id)
            assert g is not None
        db.upsert_group(g["id"], new_topic)
        replies.add(text=text.format(addr, new_topic))
        return

    g = db.get_channel(message.chat.id) or db.get_group(message.chat.id)
    if not g:
        addr = message.get_sender_contact().addr
        _add_group(bot, message.chat.id, as_admin=bot.is_admin(addr))
        g = db.get_group(message.chat.id)
        assert g is not None
    replies.add(text=g["topic"] or "-", quote=message)


@simplebot.command
def group_remove(bot: DeltaBot, args: list, message: Message, replies: Replies) -> None:
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


def cmd_chan(bot: DeltaBot, payload: str, message: Message, replies: Replies) -> None:
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


def _add_group(bot: DeltaBot, gid: int, as_admin=False) -> None:
    if as_admin or _getdefault(bot, "allow_groups") == "1":
        db.upsert_group(gid, None)
    else:
        bot.get_chat(gid).remove_contact(bot.self_contact)


def _add_contact(chat: Chat, contact: Contact) -> None:
    img_path = chat.get_profile_image()
    if img_path and not os.path.exists(img_path):
        chat.remove_profile_image()
    chat.add_contact(contact)


def _get_name(c: Contact) -> str:
    if c.name == c.addr:
        return c.addr
    return "{}({})".format(c.name, c.addr)


def _process_channels(bot: DeltaBot) -> None:
    while True:
        _send_diffusion(bot, *channel_posts.get())


def _send_diffusion(bot: DeltaBot, message: Message, chats: list) -> None:
    text = message.text
    html = message.html
    filename = message.filename
    quote = message.quote
    sender = _get_name(message.get_sender_contact())
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
    try:
        replies.send_reply_messages()
    except ValueError as err:
        bot.logger.exception(err)
