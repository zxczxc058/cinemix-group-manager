import json
import logging
import os
import sqlite3
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatMemberStatus
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ChatMemberHandler, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
OWNER_ID = int(os.environ.get('OWNER_ID', '6390241278'))
TOKEN = os.environ.get('BOT_TOKEN')
DB_PATH = os.environ.get('DB_PATH', 'cinemix_groups.sqlite3')


def connect():
    db = sqlite3.connect(DB_PATH)
    db.execute('CREATE TABLE IF NOT EXISTS groups (chat_id INTEGER PRIMARY KEY, title TEXT NOT NULL, approved INTEGER NOT NULL DEFAULT 0, block_links INTEGER NOT NULL DEFAULT 0, welcome INTEGER NOT NULL DEFAULT 1, welcome_delete_seconds INTEGER NOT NULL DEFAULT 60)')
    db.commit()
    return db


def group(chat_id):
    with connect() as db:
        return db.execute('SELECT chat_id,title,approved,block_links,welcome,welcome_delete_seconds FROM groups WHERE chat_id=?', (chat_id,)).fetchone()


def upsert(chat_id, title):
    with connect() as db:
        db.execute('INSERT INTO groups(chat_id,title) VALUES (?,?) ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title', (chat_id,title))
        db.commit()


def set_option(chat_id, field, value):
    if field not in ('approved','block_links','welcome','welcome_delete_seconds'):
        return
    with connect() as db:
        db.execute(f'UPDATE groups SET {field}=? WHERE chat_id=?', (value,chat_id))
        db.commit()


async def is_admin(update, context, chat_id):
    user = update.effective_user
    if not user:
        return False
    if user.id == OWNER_ID:
        return True
    try:
        member = await context.bot.get_chat_member(chat_id, user.id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False


def settings_keyboard(chat_id, g):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔗 חסימת קישורים: {'פעיל' if g[3] else 'כבוי'}", callback_data=f'toggle:links:{chat_id}')],
        [InlineKeyboardButton(f"👋 הודעת ברוכים הבאים: {'פעיל' if g[4] else 'כבוי'}", callback_data=f'toggle:welcome:{chat_id}')],
        [InlineKeyboardButton(f"⏱ מחיקת ברוכים הבאים: {g[5]} שניות", callback_data=f'toggle:delay:{chat_id}')],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != 'private':
        return
    if update.effective_user.id == OWNER_ID:
        await update.message.reply_text('👑 פאנל הבעלים של CINEMIX\n/groups — קבוצות ובקשות אישור\n/manage — ניהול קבוצה (שלח /manage בקבוצה)')
    else:
        await update.message.reply_text('🛡️ CINEMIX ניהול קבוצות\nהוסיפו אותי לקבוצה כמנהל. הקבוצה תופעל רק אחרי אישור בעל המערכת.\nמנהלי קבוצה מאושרת יכולים לשלוח /manage בתוך הקבוצה.')


async def groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID or update.effective_chat.type != 'private':
        return
    with connect() as db:
        rows = db.execute('SELECT chat_id,title,approved FROM groups ORDER BY approved ASC,title').fetchall()
    if not rows:
        await update.message.reply_text('עדיין לא נרשמו קבוצות.')
        return
    for chat_id, title, approved in rows:
        keys = [[InlineKeyboardButton('❌ בטל אישור', callback_data=f'approve:0:{chat_id}')]] if approved else [[InlineKeyboardButton('✅ אשר', callback_data=f'approve:1:{chat_id}'), InlineKeyboardButton('🚫 דחה', callback_data=f'approve:0:{chat_id}')]]
        await update.message.reply_text(f'{title}\nמזהה: {chat_id}\nסטטוס: {"מאושר" if approved else "ממתין"}', reply_markup=InlineKeyboardMarkup(keys))


async def my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    event = update.my_chat_member
    if not event or event.chat.type not in ('group','supergroup'):
        return
    new_status = event.new_chat_member.status
    if new_status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR):
        upsert(event.chat.id, event.chat.title or str(event.chat.id))
        g = group(event.chat.id)
        if not g[2]:
            try:
                await context.bot.send_message(OWNER_ID, f'🆕 בקשת אישור קבוצה\n{g[1]}\nID: {g[0]}', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('✅ אשר', callback_data=f'approve:1:{g[0]}'), InlineKeyboardButton('🚫 דחה', callback_data=f'approve:0:{g[0]}')]]))
            except Exception:
                logging.exception('Owner notification failed; owner must /start bot first')


async def manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ('group','supergroup'):
        await update.message.reply_text('שלח /manage בתוך הקבוצה שברצונך לנהל.')
        return
    g = group(chat.id)
    if not g or not g[2]:
        await update.message.reply_text('⏳ הקבוצה עדיין לא אושרה על ידי בעל המערכת.')
        return
    if not await is_admin(update, context, chat.id):
        await update.message.reply_text('רק מנהלי הקבוצה יכולים לשנות הגדרות.')
        return
    await update.message.reply_text('🛡️ הגדרות הקבוצה:', reply_markup=settings_keyboard(chat.id, g))


async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    parts = q.data.split(':')
    if len(parts) != 3:
        await q.answer()
        return
    action, value, id_text = parts
    try:
        chat_id = int(id_text)
    except ValueError:
        await q.answer('מזהה שגוי', show_alert=True)
        return
    g = group(chat_id)
    if not g:
        await q.answer('קבוצה לא נמצאה', show_alert=True)
        return
    if action == 'approve':
        if q.from_user.id != OWNER_ID:
            await q.answer('אין הרשאה', show_alert=True)
            return
        set_option(chat_id, 'approved', int(value))
        await q.answer('עודכן')
        await q.edit_message_text(f'{g[1]} — {"אושרה ✅" if value == "1" else "לא מאושרת 🚫"}')
        try:
            await context.bot.send_message(chat_id, '🛡️ מערכת CINEMIX הופעלה! מנהלים: /manage' if value == '1' else '🛡️ מערכת CINEMIX אינה פעילה בקבוצה זו.')
        except Exception:
            logging.exception('Could not notify group')
        return
    if action != 'toggle' or not g[2] or not await is_admin(update, context, chat_id):
        await q.answer('אין הרשאה', show_alert=True)
        return
    if value == 'links':
        set_option(chat_id, 'block_links', 0 if g[3] else 1)
    elif value == 'welcome':
        set_option(chat_id, 'welcome', 0 if g[4] else 1)
    elif value == 'delay':
        options = [0, 30, 60, 120, 300]
        set_option(chat_id, 'welcome_delete_seconds', options[(options.index(g[5]) + 1) % len(options)] if g[5] in options else 60)
    else:
        await q.answer()
        return
    await q.answer('נשמר')
    await q.edit_message_reply_markup(reply_markup=settings_keyboard(chat_id, group(chat_id)))


async def delete_welcome(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    try:
        await context.bot.delete_message(data['chat_id'], data['message_id'])
    except Exception:
        logging.exception('Could not delete welcome')


async def new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    g = group(update.effective_chat.id)
    if not g or not g[2] or not g[4]:
        return
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        msg = await update.message.reply_text(f'👋 ברוך הבא, {member.full_name}!')
        if g[5] > 0 and context.job_queue:
            context.job_queue.run_once(delete_welcome, g[5], data={'chat_id': msg.chat_id, 'message_id': msg.message_id})


async def moderate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.from_user:
        return
    g = group(update.effective_chat.id)
    if not g or not g[2] or not g[3]:
        return
    if await is_admin(update, context, update.effective_chat.id):
        return
    entities = list(msg.entities or []) + list(msg.caption_entities or [])
    link = any(e.type in ('url','text_link') for e in entities)
    content = (msg.text or msg.caption or '').lower()
    link = link or any(prefix in content for prefix in ('https://','http://','www.','t.me/'))
    if link:
        try:
            await msg.delete()
        except Exception:
            logging.exception('Delete failed; check bot admin permissions')


def main():
    if not TOKEN:
        raise RuntimeError('Set BOT_TOKEN as a Render secret environment variable')
    connect().close()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('groups', groups))
    app.add_handler(CommandHandler('manage', manage))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(ChatMemberHandler(my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.StatusUpdate.NEW_CHAT_MEMBERS, new_members))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & (filters.TEXT | filters.CAPTION) & ~filters.COMMAND, moderate))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
