import asyncio
import copy
import html
import json
import logging
import os
import re
import sqlite3
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, date, time as dt_time
from astral import Observer
from astral.sun import sun
from pyluach import dates
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import ChatPermissions, InlineKeyboardButton as B, InlineKeyboardMarkup as K, Update
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import TelegramError
from telegram.ext import (ApplicationBuilder, CallbackQueryHandler, ChatMemberHandler,
                          CommandHandler, ContextTypes, MessageHandler, filters)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('cinemix')
TOKEN = os.getenv('BOT_TOKEN')
OWNER = int(os.getenv('OWNER_ID', '6390241278'))
DB = os.getenv('DB_PATH', 'cinemix_groups.sqlite3')
TZ = ZoneInfo('Asia/Jerusalem')
FLOODS = defaultdict(deque)
PENDING = {}
LAST_WELCOME = {}

DEFAULT = {
 'links': True, 'max_warn': 3, 'welcome': True, 'welcome_text': '👋 ברוך הבא {user}!\nשמחים שהצטרפת אלינו 💜',
 'welcome_buttons': [], 'welcome_media': None, 'welcome_seconds': 300,
 'service_delete': True, 'channel_posts_delete': False, 'verify': False, 'verify_text': 'שלום {user}, לחץ על הכפתור כדי לאמת את עצמך.',
 'flood': False, 'flood_count': 5, 'flood_seconds': 10, 'flood_mute': 1800,
 'words': [], 'word_action': 'delete', 'word_mute': 1800,
 'lock_text': '🔒 הקבוצה ננעלה', 'unlock_text': '🔓 הקבוצה נפתחה',
 'shabbat': False, 'friday_time': '13:00', 'holiday': False, 'holiday_time': '14:00',
 'end_offset': 30, 'nightfall_minutes': 42, 'shabbat_lock_text': '🕯️ שבת שלום! הקבוצה ננעלה.',
 'shabbat_unlock_text': '🌟 שבוע טוב! הקבוצה נפתחה.',
 'holiday_lock_text': '🕯️ חג שמח! הקבוצה ננעלה.',
 'holiday_unlock_text': '🌟 חג שמח! הקבוצה נפתחה.',
 'daily_lock': False, 'daily_lock_time': '23:00', 'daily_unlock_time': '07:00',
 'replies': [], 'announcements': [], 'allowlist': [], 'default_lock': False,
}
HELP = {
 'links': '🔗 חסימת קישורים: קישור של משתמש רגיל נמחק והוא מקבל אזהרה. בהגעה למכסה הוא מורחק. מנהלים ומשתמשים מורשים מוחרגים. /warn בתגובה להודעה מוסיף אזהרה ידנית.',
 'welcome': '👋 ברוכים הבאים: הגדירו טקסט, כפתורים, תמונה/וידאו וזמן מחיקה. ההודעה החדשה מחליפה את הקודמת. {user} יוצר תיוג לחיץ.',
 'flood': '🛡️ אנטי ספאם: בחרו מספר הודעות, חלון זמן ומשך השתקה בשניות. עודף הודעות נמחק וגורר השתקה.',
 'words': '🚫 מילים אסורות: הגדירו רשימה מופרדת בפסיקים ובחרו פעולה: delete / warn / mute / ban.',
 'lock': '🔒 נעילה: שומרת את הרשאות ברירת המחדל של הקבוצה ומחזירה אותן בפתיחה. /lock ו-/unlock בקבוצה. ניתן להגדיר נעילה יומית.',
 'calendar': '🕯️ שבת וחג: נעילה בשעה קבועה ביום שישי או בערב חג לפי לוח ישראל. פתיחה לפי שקיעה בירושלים + דקות לצאת משוער + דקות המתנה. זהו חישוב משוער ולא זמן הלכתי מוסמך; יש לוודא התאמה למנהג הקבוצה. שבת וחג רצופים נשארים נעולים.',
 'users': '👮 ניהול משתמשים: הגיבו להודעה עם /warn [סיבה], /mute 30m [סיבה], /unmute, /ban [סיבה], /unban (לפי מזהה). /warnings בתגובה מציג אזהרות. /clean 50 מוחק הודעות אחרונות שנצפו.',
 'replies': '🤖 תגובות: הגדירו טריגר, מצב exact או contains, טקסט וכפתורים. ההודעה המקורית והתגובה נשארות.',
 'announcements': '📢 הודעות אוטומטיות: הודעות חוזרות לפי מרווח דקות. בזמן נעילה הן מושהות ולא נשלחות באיחור.',
 'verify': '✅ אימות: משתמש חדש מוגבל עד שילחץ על כפתור האימות. אין הרחקה אוטומטית. לאחר אימות תישלח ברכת הצטרפות.',
 'backup': '📦 /export בקבוצה או /export <group_id> בפרטי. שלחו את קובץ JSON לקבוצה אחרת והגיבו לו עם /import. כל ההגדרות יוחלפו לאחר אישור.',
 'channels': '📣 הודעות בשם ערוץ: הפעלה מוחקת הודעות שנשלחו בשם ערוץ או כערוץ מחובר, ולא הודעות רגילות של משתמשים. מנהלים יכולים לשנות בפרטי.',
 'allowlist': '🛡️ משתמשים מורשים: /allow בתגובה להודעת משתמש, /unallow להסרה. הם פטורים מחסימת קישורים ואנטי-ספאם.',
}


def conn():
    p = Path(DB)
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    # Migrate the original small CINEMIX database without losing approvals.
    old_columns=[r[1] for r in c.execute('PRAGMA table_info(groups)')]
    if old_columns and 'chat_id' in old_columns and 'id' not in old_columns:
        c.execute('ALTER TABLE groups RENAME TO groups_legacy')
    c.execute('CREATE TABLE IF NOT EXISTS groups (id INTEGER PRIMARY KEY, title TEXT, approved INTEGER DEFAULT 0, settings TEXT, locked INTEGER DEFAULT 0, permissions TEXT, lock_reason TEXT, last_announcement INTEGER DEFAULT 0, active INTEGER DEFAULT 1)')
    if 'active' not in [r[1] for r in c.execute('PRAGMA table_info(groups)')]:
        c.execute('ALTER TABLE groups ADD COLUMN active INTEGER DEFAULT 1')
    legacy=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='groups_legacy'")]
    if legacy:
        for old in c.execute('SELECT * FROM groups_legacy').fetchall():
            initial=copy.deepcopy(DEFAULT)
            initial.update(links=bool(old['block_links']),welcome=bool(old['welcome']),welcome_seconds=int(old['welcome_delete_seconds']))
            c.execute('INSERT OR IGNORE INTO groups(id,title,approved,settings) VALUES (?,?,?,?)',
                      (old['chat_id'],old['title'],old['approved'],json.dumps(initial,ensure_ascii=False)))
        c.execute('DROP TABLE groups_legacy')
    c.execute('CREATE TABLE IF NOT EXISTS warnings (chat INTEGER, uid INTEGER, count INTEGER DEFAULT 0, PRIMARY KEY(chat,uid))')
    c.execute('CREATE TABLE IF NOT EXISTS seen (chat INTEGER, mid INTEGER, ts INTEGER, PRIMARY KEY(chat,mid))')
    c.execute('CREATE TABLE IF NOT EXISTS pending_verify (chat INTEGER, uid INTEGER, PRIMARY KEY(chat,uid))')
    c.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, val TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS welcomes (chat INTEGER PRIMARY KEY, mid INTEGER, expires INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS mutes (chat INTEGER, uid INTEGER, original TEXT, PRIMARY KEY(chat,uid))')
    c.execute('CREATE TABLE IF NOT EXISTS pending_edits (uid INTEGER PRIMARY KEY, chat INTEGER, field TEXT)')
    c.commit()
    return c


def get_group(cid):
    with conn() as c:
        r = c.execute('SELECT * FROM groups WHERE id=?',(cid,)).fetchone()
    return dict(r) if r else None


def owner_defaults():
    with conn() as c:r=c.execute("SELECT val FROM meta WHERE key='owner_defaults'").fetchone()
    if r:
        try:return {**copy.deepcopy(DEFAULT),**json.loads(r['val'])}
        except (ValueError,TypeError):pass
    return copy.deepcopy(DEFAULT)


def cfg(cid):
    r = get_group(cid)
    if not r: return copy.deepcopy(DEFAULT)
    try: data=json.loads(r['settings'] or '{}')
    except Exception: data={}
    return {**copy.deepcopy(DEFAULT), **data}


def save_cfg(cid, data):
    with conn() as c:
        c.execute('UPDATE groups SET settings=? WHERE id=?',(json.dumps(data,ensure_ascii=False),cid))
        c.commit()


def set_cfg(cid, key, value):
    d=cfg(cid); d[key]=value; save_cfg(cid,d)


def upsert(cid,title):
    initial=owner_defaults()
    with conn() as c:
        c.execute('INSERT INTO groups(id,title,settings,active) VALUES (?,?,?,1) ON CONFLICT(id) DO UPDATE SET title=excluded.title, active=1',(cid,title,json.dumps(initial,ensure_ascii=False)))
        c.commit()


def set_group(cid, **kw):
    allowed={'approved','locked','permissions','lock_reason','last_announcement','active'}
    kw={k:v for k,v in kw.items() if k in allowed}
    if not kw:return
    with conn() as c:
        c.execute('UPDATE groups SET '+','.join(k+'=?' for k in kw)+' WHERE id=?',(*kw.values(),cid));c.commit()


def all_groups():
    with conn() as c: return [dict(x) for x in c.execute('SELECT * FROM groups WHERE active=1 ORDER BY title')]


def warn_count(cid,uid,delta=0):
    with conn() as c:
        c.execute('INSERT OR IGNORE INTO warnings(chat,uid,count) VALUES (?,?,0)',(cid,uid))
        if delta:c.execute('UPDATE warnings SET count=MAX(0,count+?) WHERE chat=? AND uid=?',(delta,cid,uid))
        n=c.execute('SELECT count FROM warnings WHERE chat=? AND uid=?',(cid,uid)).fetchone()[0]
        c.commit()
    return n


def mention(user):
    return f'<a href="tg://user?id={user.id}">{html.escape(user.full_name)}</a>'


def mention_id(uid,name=None):
    return f'<a href="tg://user?id={uid}">{html.escape(name or str(uid))}</a>'


def render_text(text, user=None):
    s=(text[5:] if isinstance(text,str) and text.startswith('HTML:') else html.escape(text or ''))
    if user:s=s.replace('{user}',mention(user)).replace('{name}',html.escape(user.full_name))
    return s


def buttons(rows):
    kb=[]
    for item in rows or []:
        if isinstance(item,dict) and str(item.get('url','')).startswith(('https://','http://','tg://')):
            kb.append([B(str(item.get('text','קישור'))[:60],url=item['url'])])
    return K(kb) if kb else None


def kb(*rows): return K([[B(label,callback_data=data) for label,data in row] for row in rows])


async def authorized(bot,uid,cid):
    if uid==OWNER:return True
    try:
        m=await bot.get_chat_member(cid,uid)
        return m.status in (ChatMemberStatus.ADMINISTRATOR,ChatMemberStatus.OWNER)
    except TelegramError:return False


async def send_formatted(bot,cid,text,user=None,markup=None,media=None,reply_to=None):
    txt=render_text(text,user)
    kw={'parse_mode':ParseMode.HTML,'reply_markup':markup}
    if reply_to:kw['reply_to_message_id']=reply_to
    if media:
        try:
            if media.get('type')=='photo':return await bot.send_photo(cid,media['id'],caption=txt[:1024],**kw)
            if media.get('type')=='video':return await bot.send_video(cid,media['id'],caption=txt[:1024],**kw)
        except TelegramError:log.exception('Media send failed; using text')
    return await bot.send_message(cid,txt[:4096],**kw)


async def safe_delete(bot,cid,mid):
    try:await bot.delete_message(cid,mid)
    except TelegramError:pass


async def notify_owner(bot,cid):
    g=get_group(cid)
    if not g:return
    try:
        await bot.send_message(OWNER,f'📥 בקשת אישור חדשה\n{g["title"]}\nID: {cid}',reply_markup=kb([('✅ אישור',f'approval:1:{cid}'),('❌ דחייה',f'approval:0:{cid}')]))
    except TelegramError:log.exception('Owner notification')


async def my_member(update,context):
    ev=update.my_chat_member
    if not ev or ev.chat.type not in ('group','supergroup'):
        return
    before=ev.old_chat_member.status
    after=ev.new_chat_member.status
    active=(ChatMemberStatus.MEMBER,ChatMemberStatus.ADMINISTRATOR,ChatMemberStatus.OWNER)
    if after in active:
        old=get_group(ev.chat.id)
        upsert(ev.chat.id,ev.chat.title or str(ev.chat.id))
        if not old:
            await notify_owner(context.bot,ev.chat.id)
    elif after in (ChatMemberStatus.LEFT,ChatMemberStatus.BANNED) and before in active:
        # Preserve approval and settings across a temporary removal or restart.
        set_group(ev.chat.id, active=0)
        log.info('Bot removed from group %s (settings retained)',ev.chat.id)


async def ensure_group(bot,chat,notify=True):
    """Recover a missing group row only when Telegram confirms this bot is present."""
    if chat.type not in ('group','supergroup'):
        return False
    existing=get_group(chat.id)
    if existing:
        if chat.title and existing['title'] != chat.title:
            upsert(chat.id,chat.title)
        if not existing.get('active', 1):
            # An old group is not silently reactivated by unrelated service messages.
            try:
                me=await bot.get_me()
                member=await bot.get_chat_member(chat.id,me.id)
                if member.status not in (ChatMemberStatus.MEMBER,ChatMemberStatus.ADMINISTRATOR,ChatMemberStatus.OWNER):
                    return False
            except TelegramError:
                return False
            set_group(chat.id,active=1)
        return True
    try:
        me=await bot.get_me()
        membership=await bot.get_chat_member(chat.id,me.id)
        if membership.status not in (ChatMemberStatus.MEMBER,ChatMemberStatus.ADMINISTRATOR,ChatMemberStatus.OWNER):
            return False
    except TelegramError as e:
        log.warning('Cannot confirm membership in %s: %s',chat.id,e)
        return False
    upsert(chat.id,chat.title or str(chat.id))
    log.info('Recovered missing group %s',chat.id)
    if notify:
        await notify_owner(bot,chat.id)
    return True


def menu(cid):
    g=get_group(cid)
    if not g:return None
    return kb([('🔗 קישורים',f'page:links:{cid}'),('👋 ברוכים הבאים',f'page:welcome:{cid}')],
              [('🛡️ אנטי ספאם',f'page:flood:{cid}'),('🚫 מילים אסורות',f'page:words:{cid}')],
              [('🔒 נעילה',f'page:lock:{cid}'),('🕯️ שבת וחג',f'page:calendar:{cid}')],
              [('👮 משתמשים',f'page:users:{cid}'),('✅ אימות',f'page:verify:{cid}')],
              [('🤖 תגובות',f'page:replies:{cid}'),('📢 הודעות חוזרות',f'page:announcements:{cid}')],
              [('🛡️ מורשים',f'page:allowlist:{cid}'),('📣 הודעות ערוץ',f'page:channels:{cid}')],
              [('📦 גיבוי',f'page:backup:{cid}'),('🗑️ הודעות שירות',f'page:service:{cid}')],
              [('📖 מדריך',f'page:guide:{cid}'),('⬅️ קבוצות',f'list:all:0')])


async def list_groups(bot,uid,cid):
    groups=[]
    for g in all_groups():
        if uid==OWNER or (g['approved'] and await authorized(bot,uid,g['id'])):groups.append(g)
    if not groups:
        if uid==OWNER:
            await bot.send_message(cid,'אין כרגע קבוצות פעילות ברשימה. אם הבוט נמצא בקבוצה, שלח בה /register כדי לרשום אותה מחדש.')
        return
    for g in groups:
        title=g['title'][:50]
        text=f'👥 {title}\nסטטוס: {"מאושרת" if g["approved"] else "ממתינה לאישור"}'
        row=[('⚙️ ניהול',f'open:x:{g["id"]}')]
        if uid==OWNER:row.append(('❌ ביטול' if g['approved'] else '✅ אישור',f'approval:{0 if g["approved"] else 1}:{g["id"]}'))
        await bot.send_message(cid,text,reply_markup=kb(row))


def regular_start_text():
    with conn() as c:
        r=c.execute("SELECT val FROM meta WHERE key='regular_start_text'").fetchone()
    return r['val'] if r else '🛡️ ברוכים הבאים לבוט CINEMIX לניהול קבוצות!\nלחץ על הקבוצות שלי כדי להתחיל.'


async def owner_panel(update,context):
    if update.effective_chat.type!='private' or update.effective_user.id!=OWNER:
        return
    await update.message.reply_text('👑 פאנל הבעלים של CINEMIX\n/groups — כל הקבוצות\n/setstart טקסט — שינוי הודעת הפתיחה\n/showstart — הצגת הודעת הפתיחה\n\nאם קבוצה חסרה אחרי פריסה, שלח בה /register פעם אחת. אישור נדרש רק לקבוצה חדשה.',reply_markup=kb([('👥 כל הקבוצות','list:all:0')],[('📖 מדריך','guide:all:0')]))
    await list_groups(context.bot,OWNER,update.effective_chat.id)


async def set_start_text(update,context):
    if update.effective_chat.type!='private' or update.effective_user.id!=OWNER:return
    value=update.message.text.partition(' ')[2].strip()
    if not value:
        with conn() as c:
            c.execute("INSERT OR REPLACE INTO pending_edits(uid,chat,field) VALUES (?,0,'owner_start_text')",(OWNER,));c.commit()
        await update.message.reply_text('✏️ שלח עכשיו בהודעה רגילה את טקסט הפתיחה למשתמשים. /cancel לביטול.')
        return
    if len(value)>3500:
        await update.message.reply_text('הטקסט ארוך מדי (עד 3500 תווים).')
        return
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO meta(key,val) VALUES ('regular_start_text',?)",(value,));c.commit()
    await update.message.reply_text('✅ הודעת הפתיחה עודכנה.')


async def show_start_text(update,context):
    if update.effective_chat.type!='private' or update.effective_user.id!=OWNER:return
    await update.message.reply_text(regular_start_text())


async def start(update,context):
    if update.effective_chat.type!='private':return
    if update.effective_user.id==OWNER:
        await owner_panel(update,context)
    else:
        # Ordinary users only see the owner's welcome message, not management menus.
        await update.message.reply_text(regular_start_text())


async def manage(update,context):
    chat=update.effective_chat;uid=update.effective_user.id
    if chat.type!='private':
        await safe_delete(context.bot,chat.id,update.message.message_id)
        if not await ensure_group(context.bot,chat):
            return
        if not await authorized(context.bot,uid,chat.id):return
        try:await context.bot.send_message(uid,'⚙️ ניהול קבוצות:',reply_markup=kb([('👥 בחר קבוצה','list:all:0')]))
        except TelegramError:
            await context.bot.send_message(chat.id,'פתח תחילה את הבוט בפרטי ולחץ Start.')
    else:
        if uid==OWNER or any(g['approved'] and await authorized(context.bot,uid,g['id']) for g in all_groups()):
            await list_groups(context.bot,uid,chat.id)


async def groups_cmd(update,context):
    if update.effective_chat.type=='private' and update.effective_user.id==OWNER:
        await list_groups(context.bot,OWNER,update.effective_chat.id)


async def track_group(update,context):
    chat=update.effective_chat
    if not chat or chat.type not in ('group','supergroup'):
        return
    # Membership transitions are handled exclusively by MY_CHAT_MEMBER.
    # A left_chat_member service message must never create a new approval request.
    msg=update.effective_message
    if msg and (msg.left_chat_member or msg.new_chat_members):
        return
    await ensure_group(context.bot,chat)


async def register_group(update,context):
    """Explicit group recovery after a database reset."""
    chat=update.effective_chat
    if chat.type not in ('group','supergroup'):
        return
    user=update.effective_user
    if not user or not await authorized(context.bot,user.id,chat.id):
        return
    await safe_delete(context.bot,chat.id,update.message.message_id)
    if not await ensure_group(context.bot,chat):
        return
    g=get_group(chat.id)
    await context.bot.send_message(chat.id,
        '✅ הקבוצה נרשמה במערכת. ' + ('הקבוצה מאושרת.' if g['approved'] else 'ממתינה לאישור בעל הבוט.'))


def page_keyboard(cid,page):
    d=cfg(cid)
    toggles={'links':'links','welcome':'welcome','flood':'flood','verify':'verify','service':'service_delete','calendar':'shabbat','channels':'channel_posts_delete'}
    rows=[]
    if page in toggles:
        key=toggles[page];rows.append([('🟢 פעיל' if d[key] else '🔴 כבוי',f'toggle:{key}:{cid}')])
    if page=='links':rows.append([(f'⚠️ אזהרות: {d["max_warn"]}',f'edit:max_warn:{cid}')])
    if page=='welcome':
        rows.extend([[('✏️ טקסט ברוכים הבאים',f'edit:welcome_text:{cid}')],
                     [('🔘 כפתורים',f'edit:welcome_buttons:{cid}')],
                     [(f'⏱️ זמן מחיקה: {d["welcome_seconds"]} שניות',f'edit:welcome_seconds:{cid}')],
                     [('🖼️ תמונה / וידאו',f'edit:welcome_media:{cid}')]])
    if page=='flood':
        for key,label in [('flood_count','מספר הודעות'),('flood_seconds','חלון זמן בשניות'),('flood_mute','השתקה בשניות')]:rows.append([(f'{label}: {d[key]}',f'edit:{key}:{cid}')])
    if page=='words':
        rows.extend([[('📝 רשימת מילים',f'edit:words:{cid}')],[(f'⚖️ עונש: {d["word_action"]}',f'cycle:word_action:{cid}')],[('⏱️ זמן השתקה',f'edit:word_mute:{cid}')]])
    if page=='lock':
        rows.extend([[('🔒 נעל עכשיו',f'lock:manual:{cid}'),('🔓 פתח עכשיו',f'unlock:manual:{cid}')],
                     [('✏️ הודעת נעילה',f'edit:lock_text:{cid}')],[('✏️ הודעת פתיחה',f'edit:unlock_text:{cid}')],
                     [('⏰ נעילה יומית',f'toggle:daily_lock:{cid}')],
                     [('🕐 שעת נעילה יומית',f'edit:daily_lock_time:{cid}')],
                     [('🕐 שעת פתיחה יומית',f'edit:daily_unlock_time:{cid}')]])
    if page=='calendar':
        rows.extend([[('🕯️ שבת פעיל/כבוי',f'toggle:shabbat:{cid}'),('✡️ חג פעיל/כבוי',f'toggle:holiday:{cid}')],
                     [('🕐 שעת נעילת שישי',f'edit:friday_time:{cid}')],[('🕐 שעת נעילת ערב חג',f'edit:holiday_time:{cid}')],
                     [('⏱️ דקות אחרי צאת',f'edit:end_offset:{cid}')],
                     [('🌇 דקות אחרי שקיעה לצאת משוער',f'edit:nightfall_minutes:{cid}')]])
        for key,label in [('shabbat_lock_text','הודעת כניסת שבת'),('shabbat_unlock_text','הודעת צאת שבת'),('holiday_lock_text','הודעת כניסת חג'),('holiday_unlock_text','הודעת צאת חג')]:rows.append([(label,f'edit:{key}:{cid}')])
    if page=='replies':rows.extend([[('➕ הוספת תגובה',f'edit:add_reply:{cid}')],[('📋 רשימת תגובות / עריכה / מחיקה',f'show:replies:{cid}')]])
    if page=='announcements':rows.extend([[('➕ הוספת הודעה חוזרת',f'edit:add_announcement:{cid}')],[('📋 רשימה / עריכה / מחיקה',f'show:announcements:{cid}')]])
    if page=='allowlist':rows.append([('📋 רשימת מורשים',f'show:allowlist:{cid}')])
    if page=='backup':
        rows.append([('📤 ייצוא הגדרות',f'export:x:{cid}')])
        rows.append([('👑 שמור כברירת מחדל לכל קבוצה חדשה',f'defaults:x:{cid}')])
    if page=='users':rows.append([('📖 פקודות משתמשים',f'help:users:{cid}')])
    rows.append([('⬅️ חזרה להגדרות',f'open:x:{cid}')])
    return kb(*rows)


async def callbacks(update,context):
    q=update.callback_query;uid=q.from_user.id
    try:action,value,cs=q.data.split(':',2);cid=int(cs)
    except Exception:await q.answer('שגיאה');return
    if action=='list':
        await q.answer();await list_groups(context.bot,uid,q.message.chat_id);return
    if action=='guide':
        if uid!=OWNER and not any(g['approved'] and await authorized(context.bot,uid,g['id']) for g in all_groups()):
            await q.answer('אין הרשאה',show_alert=True);return
        await q.answer();await q.message.reply_text('📖 מדריך CINEMIX\n\n'+'\n\n'.join(HELP.values())[:3900]);return
    if action=='approval':
        if uid!=OWNER:await q.answer('רק בעל הבוט',show_alert=True);return
        if not get_group(cid):await q.answer('קבוצה לא נמצאה');return
        set_group(cid,approved=int(value));await q.answer('עודכן')
        await q.edit_message_text(f'👑 הקבוצה {get_group(cid)["title"]}: {"מאושרת" if value=="1" else "לא מאושרת"}')
        return
    g=get_group(cid)
    if not g or not g.get('active',1):
        await q.answer('הקבוצה לא פעילה כרגע. שלח /register בקבוצה כדי לרשום אותה.',show_alert=True);return
    if not g['approved'] and uid!=OWNER:
        await q.answer('הקבוצה ממתינה לאישור בעל הבוט.',show_alert=True);return
    if action=='verify':
        if int(value)!=uid:await q.answer('הכפתור מיועד למשתמש אחר',show_alert=True);return
        with conn() as c:
            exists=c.execute('SELECT 1 FROM pending_verify WHERE chat=? AND uid=?',(cid,uid)).fetchone()
        if not exists:await q.answer('כבר אומת');return
        try:
            await context.bot.restrict_chat_member(cid,uid,permissions=await member_permissions(context.bot,cid))
            with conn() as c:c.execute('DELETE FROM pending_verify WHERE chat=? AND uid=?',(cid,uid));c.commit()
            await q.answer('אומתת בהצלחה!');await q.message.delete()
            if cfg(cid)['welcome']:await welcome(context.bot,cid,q.from_user,context)
        except TelegramError:await q.answer('שגיאה באימות',show_alert=True)
        return
    if not await authorized(context.bot,uid,cid):
        await q.answer('אין הרשאה',show_alert=True);return
    if action=='open':
        await q.answer();await q.message.reply_text(f'⚙️ {g["title"]}\nבחר הגדרה:',reply_markup=menu(cid));return
    if action=='page':
        await q.answer()
        desc=HELP.get(value,'בחר פעולה בתפריט. ההגדרות יישמרו לקבוצה זו בלבד.')
        if value=='guide':desc='\n\n'.join(HELP.values())[:3900]
        await q.message.reply_text(desc,reply_markup=page_keyboard(cid,value) if value!='guide' else None)
        return
    if action=='help':await q.answer();await q.message.reply_text(HELP.get(value,''));return
    if action=='toggle':
        if value not in ('links','welcome','flood','verify','service_delete','channel_posts_delete','shabbat','holiday','daily_lock'):await q.answer('לא נתמך');return
        set_cfg(cid,value,not cfg(cid)[value]);await q.answer('נשמר')
        await q.message.reply_text('✅ ההגדרה עודכנה.',reply_markup=menu(cid));return
    if action=='cycle' and value=='word_action':
        opts=['delete','warn','mute','ban'];cur=cfg(cid)['word_action'];set_cfg(cid,'word_action',opts[(opts.index(cur)+1)%len(opts)]);await q.answer('נשמר');return
    if action=='edit':
        if q.message.chat.type!='private':
            await q.answer('עריכת הגדרות בפרטי בלבד',show_alert=True);return
        PENDING[uid]=(cid,value)
        with conn() as c:
            c.execute('INSERT OR REPLACE INTO pending_edits(uid,chat,field) VALUES (?,?,?)',(uid,cid,value));c.commit()
        await q.answer()
        await context.bot.send_message(uid,f'✏️ הגדרה: {value}\nשלח את הערך החדש בהודעה הבאה בפרטי.\nלכפתורים: שורה לכל כפתור בפורמט: כותרת | https://example.com\nלמילים אסורות: רשימה מופרדת בפסיקים.\nלתגובה חדשה: טריגר | exact/contains | טקסט\nלהודעה חוזרת: דקות | טקסט\nשלח /cancel לביטול.')
        return
    if action=='show':
        await q.answer();data=cfg(cid).get(value,[])
        if not data:await q.message.reply_text('הרשימה ריקה.');return
        for i,item in enumerate(data):
            actions=[[('🗑️ מחק',f'remove:{value},{i}:{cid}')]]
            if value in ('replies','announcements'):
                actions.append([('✏️ ערוך טקסט',f'itemedit:{value},{i}:{cid}')])
                actions.append([('🔘 כפתורים',f'itembuttons:{value},{i}:{cid}'),('🖼️ מדיה',f'itemmedia:{value},{i}:{cid}')])
            await q.message.reply_text(f'{i+1}. {str(item)[:250]}',reply_markup=kb(*actions) if value!='allowlist' else None)
        return
    if action in ('itembuttons','itemmedia'):
        try:key,index=value.split(',');index=int(index);assert key in ('replies','announcements');cfg(cid)[key][index]
        except Exception:await q.answer('לא נמצא');return
        PENDING[uid]=(cid,f'{action}:{key}:{index}')
        with conn() as c:
            c.execute('INSERT OR REPLACE INTO pending_edits(uid,chat,field) VALUES (?,?,?)',(uid,cid,f'{action}:{key}:{index}'));c.commit()
        await q.answer()
        await context.bot.send_message(uid,'🔘 שלח כפתורים בשורות: כותרת | https://example.com\nאו שלח תמונה/וידאו. כתוב מחק להסרת מדיה/כפתורים.');return
    if action=='itemedit':
        try:key,index=value.split(',');index=int(index);item=cfg(cid)[key][index]
        except Exception:await q.answer('לא נמצא');return
        PENDING[uid]=(cid,f'item:{key}:{index}')
        with conn() as c:
            c.execute('INSERT OR REPLACE INTO pending_edits(uid,chat,field) VALUES (?,?,?)',(uid,cid,f'item:{key}:{index}'));c.commit()
        await q.answer();await context.bot.send_message(uid,'✏️ שלח הגדרה חדשה:\nלתגובה: טריגר | exact/contains | טקסט\nלהודעה חוזרת: דקות | טקסט\nהעיצוב של טלגרם נשמר בהודעות טקסט.');return
    if action=='remove':
        try:key,index=value.split(',');index=int(index);data=cfg(cid)[key];data.pop(index);set_cfg(cid,key,data)
        except Exception:await q.answer('לא נמצא');return
        await q.answer('נמחק');await q.edit_message_text('🗑️ הפריט נמחק');return
    if action=='defaults':
        if uid!=OWNER:await q.answer('רק בעל הבוט',show_alert=True);return
        with conn() as c:c.execute("INSERT OR REPLACE INTO meta(key,val) VALUES ('owner_defaults',?)",(json.dumps(cfg(cid),ensure_ascii=False),));c.commit()
        await q.answer('נשמר');await q.message.reply_text('👑 הגדרות הקבוצה נשמרו כברירת מחדל לקבוצות חדשות.');return
    if action=='export':
        await q.answer();await export_file(context.bot,uid,cid);return
    if action=='import':
        item=PENDING.pop(('import',uid,cid),None)
        if not item:await q.answer('הקובץ לא נמצא');return
        save_cfg(cid,item);await q.answer('יובא');await q.edit_message_text('✅ כל הגדרות הקבוצה הוחלפו בהצלחה.');return
    if action=='warncancel':
        try:target=int(value);n=warn_count(cid,target,-1)
        except Exception:await q.answer('שגיאה');return
        await q.answer('בוטל');await q.edit_message_reply_markup(None)
        await context.bot.send_message(cid,f'✅ למשתמש {mention_id(target)} הוסרה אזהרה על ידי המנהל {mention(q.from_user)}.\nאזהרות נוכחיות: {n}/{cfg(cid)["max_warn"]}',parse_mode=ParseMode.HTML);return
    if action=='unmute':
        try:target=int(value);await context.bot.restrict_chat_member(cid,target,permissions=await member_permissions(context.bot,cid))
        except TelegramError:await q.answer('לא ניתן לבטל השתקה',show_alert=True);return
        await q.answer('בוטל');await q.edit_message_reply_markup(None)
        await context.bot.send_message(cid,f'🔊 ההשתקה של {mention_id(target)} בוטלה על ידי {mention(q.from_user)}',parse_mode=ParseMode.HTML);return
    if action in ('lock','unlock'):
        await q.answer();await change_lock(context.bot,cid,action=='lock','manual');return
    await q.answer()


def clear_pending(uid):
    PENDING.pop(uid,None)
    with conn() as c:
        c.execute('DELETE FROM pending_edits WHERE uid=?',(uid,));c.commit()


async def input_private(update,context):
    if update.effective_chat.type!='private':return
    uid=update.effective_user.id
    # Read from the database first: in-memory state is lost on deployment.
    with conn() as c:
        r=c.execute('SELECT chat,field FROM pending_edits WHERE uid=?',(uid,)).fetchone()
    pending=(r['chat'],r['field']) if r else PENDING.get(uid)
    log.info('Private input from user %s: pending field=%s',uid,pending[1] if pending else None)
    if not pending:
        if uid==OWNER:
            await update.message.reply_text('ℹ️ אין כרגע הגדרה שממתינה לערך. בחר הגדרה בתפריט, או שלח /setstart כדי לשנות את הודעת הפתיחה.')
        return
    cid,key=pending
    if key=='owner_start_text':
        if uid!=OWNER:return
        value=(update.message.text or update.message.caption or '').strip()
        if not value or len(value)>3500:
            await update.message.reply_text('❌ שלח טקסט באורך 1–3500 תווים. ההגדרה עדיין ממתינה.')
            return
        with conn() as c:
            c.execute("INSERT OR REPLACE INTO meta(key,val) VALUES ('regular_start_text',?)",(value,))
            c.execute('DELETE FROM pending_edits WHERE uid=?',(uid,));c.commit()
        PENDING.pop(uid,None)
        await update.message.reply_text('✅ הודעת הפתיחה למשתמשים נשמרה!')
        return
    group=get_group(cid)
    if not group or not group.get('active',1) or (uid!=OWNER and (not group['approved'] or not await authorized(context.bot,uid,cid))):
        await update.message.reply_text('❌ אין גישה לקבוצה הזאת כרגע.')
        return
    raw=update.message.text or update.message.caption or ''
    d=cfg(cid)
    try:
        if key in ('max_warn','welcome_seconds','flood_count','flood_seconds','flood_mute','word_mute','end_offset','nightfall_minutes'):
            val=int(raw);assert 0<=val<=86400
            if key in ('max_warn','flood_count','flood_seconds'):assert val>0
        elif key in ('friday_time','holiday_time','daily_lock_time','daily_unlock_time'):
            assert re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d',raw);val=raw
        elif key in ('welcome_buttons',):
            val=[]
            for line in raw.splitlines():
                name,url=line.split('|',1);name=name.strip();url=url.strip()
                assert url.startswith(('https://','http://','tg://'))
                val.append({'text':name,'url':url})
        elif key=='words':val=[x.strip().lower() for x in raw.split(',') if x.strip()]
        elif key=='welcome_media':
            if update.message.photo:val={'type':'photo','id':update.message.photo[-1].file_id}
            elif update.message.video:val={'type':'video','id':update.message.video.file_id}
            elif raw.lower() in ('remove','מחק'):val=None
            else:raise ValueError('שלח תמונה או וידאו')
        elif key.startswith(('itembuttons:','itemmedia:')):
            action,kind,index=key.split(':');index=int(index)
            if action=='itembuttons':
                val=[]
                if raw.strip() not in ('מחק','remove'):
                    for line in raw.splitlines():
                        name,url=line.split('|',1);name=name.strip();url=url.strip()
                        assert url.startswith(('https://','http://','tg://')) and name
                        val.append({'text':name,'url':url})
                d[kind][index]['buttons']=val
            else:
                if update.message.photo:val={'type':'photo','id':update.message.photo[-1].file_id}
                elif update.message.video:val={'type':'video','id':update.message.video.file_id}
                elif raw.strip() in ('מחק','remove'):val=None
                else:raise ValueError()
                d[kind][index]['media']=val
            save_cfg(cid,d);clear_pending(uid);await update.message.reply_text('✅ נשמר');return
        elif key.startswith('item:'):
            _,kind,index=key.split(':');index=int(index)
            if kind=='replies':
                trigger,mode,response=[x.strip() for x in raw.split('|',2)]
                assert trigger and mode in ('exact','contains') and response
                d[kind][index].update(trigger=trigger,mode=mode,text=response)
            elif kind=='announcements':
                minutes,response=raw.split('|',1);minutes=int(minutes);assert minutes>0
                d[kind][index].update(minutes=minutes,text=response.strip(),last=int(time.time()))
            save_cfg(cid,d);clear_pending(uid);await update.message.reply_text('✅ נערך בהצלחה');return
        elif key=='add_reply':
            trigger,mode,response=[x.strip() for x in raw.split('|',2)]
            assert mode in ('exact','contains') and trigger and response
            d['replies'].append({'trigger':trigger,'mode':mode,'text':response,'buttons':[]});save_cfg(cid,d)
            clear_pending(uid);await update.message.reply_text('✅ התגובה נוספה');return
        elif key=='add_announcement':
            minutes,response=raw.split('|',1);minutes=int(minutes.strip());assert minutes>=1
            d['announcements'].append({'minutes':minutes,'text':response.strip(),'last':int(time.time())});save_cfg(cid,d)
            clear_pending(uid);await update.message.reply_text('✅ ההודעה החוזרת נוספה');return
        else:val='HTML:'+update.message.text_html if update.message.text and update.message.entities else raw
        set_cfg(cid,key,val)
        clear_pending(uid)
        await update.message.reply_text('✅ נשמר בהצלחה!')
    except Exception:
        log.exception('Private input validation failed for field %s',key)
        await update.message.reply_text('❌ פורמט לא תקין. ההגדרה עדיין ממתינה — שלח ערך תקין או /cancel.')


async def cancel(update,context):
    PENDING.pop(update.effective_user.id,None)
    clear_pending(update.effective_user.id)
    await update.message.reply_text('בוטל.')


async def welcome(bot,cid,user,context):
    d=cfg(cid)
    old=LAST_WELCOME.pop(cid,None)
    with conn() as c:previous=c.execute('SELECT mid FROM welcomes WHERE chat=?',(cid,)).fetchone()
    if previous:await safe_delete(bot,cid,previous['mid'])
    if old:
        await safe_delete(bot,cid,old[0]);
        if old[1]:old[1].schedule_removal()
    msg=await send_formatted(bot,cid,d['welcome_text'],user,buttons(d['welcome_buttons']),d['welcome_media'])
    job=None
    if d['welcome_seconds']>0 and context.job_queue:
        job=context.job_queue.run_once(delete_welcome,d['welcome_seconds'],data={'cid':cid,'mid':msg.message_id})
    LAST_WELCOME[cid]=(msg.message_id,job)
    with conn() as c:c.execute('INSERT OR REPLACE INTO welcomes VALUES (?,?,?)',(cid,msg.message_id,int(time.time())+int(d['welcome_seconds'])));c.commit()


async def delete_welcome(context):
    cid=context.job.data['cid'];mid=context.job.data['mid']
    if LAST_WELCOME.get(cid,(None,))[0]==mid:
        await safe_delete(context.bot,cid,mid);LAST_WELCOME.pop(cid,None)
        with conn() as c:c.execute('DELETE FROM welcomes WHERE chat=? AND mid=?',(cid,mid));c.commit()


async def new_members(update,context):
    msg=update.message;cid=msg.chat_id;g=get_group(cid)
    if not g or not g['approved']:return
    d=cfg(cid)
    if d['service_delete']:await safe_delete(context.bot,cid,msg.message_id)
    for user in msg.new_chat_members:
        if user.is_bot:continue
        if d['verify']:
            try:
                await context.bot.restrict_chat_member(cid,user.id,permissions=ChatPermissions(can_send_messages=False))
                with conn() as c:c.execute('INSERT OR IGNORE INTO pending_verify VALUES (?,?)',(cid,user.id));c.commit()
                await send_formatted(context.bot,cid,d['verify_text'],user,kb([('✅ אני לא רובוט',f'verify:{user.id}:{cid}')]))
            except TelegramError:log.exception('Verification permissions missing')
        elif d['welcome']:await welcome(context.bot,cid,user,context)


async def service(update,context):
    cid=update.effective_chat.id;g=get_group(cid)
    if g and g['approved'] and cfg(cid)['service_delete']:
        await safe_delete(context.bot,cid,update.effective_message.message_id)


async def warning(bot,cid,user,reason=''):
    d=cfg(cid);n=warn_count(cid,user.id,1)
    txt=f'⚠️ המשתמש {mention(user)}, זוהי אזהרה {n}/{d["max_warn"]}'
    if reason:txt+=f'\n📋 סיבה: {html.escape(reason)}'
    if n>=d['max_warn']:
        try:
            await bot.ban_chat_member(cid,user.id)
            txt+='\n🚫 המשתמש הורחק לאחר שהגיע למכסת האזהרות.'
        except TelegramError:txt+='\n⚠️ לא הצלחתי להרחיק; בדוק הרשאות.'
        await bot.send_message(cid,txt,parse_mode=ParseMode.HTML)
    else:
        await bot.send_message(cid,txt,parse_mode=ParseMode.HTML,reply_markup=kb([('❌ ביטול אזהרה',f'warncancel:{user.id}:{cid}')]))


def duration(s):
    m=re.fullmatch(r'(\d+)([mhd])',s.lower())
    if not m:return None
    return int(m[1])*{'m':60,'h':3600,'d':86400}[m[2]]


async def mute(bot,cid,user,seconds,reason=''):
    try:
        await bot.restrict_chat_member(cid,user.id,permissions=ChatPermissions(can_send_messages=False),until_date=datetime.now(TZ)+timedelta(seconds=max(31,seconds)))
        txt=f'🔇 המשתמש {mention(user)} הושתק למשך {seconds//60} דקות.'
        if reason:txt+=f'\n📋 סיבה: {html.escape(reason)}'
        await bot.send_message(cid,txt,parse_mode=ParseMode.HTML,reply_markup=kb([('🔊 ביטול השתקה',f'unmute:{user.id}:{cid}')]))
    except TelegramError:log.exception('Mute failed')


async def moderate(update,context):
    msg=update.effective_message;cid=msg.chat_id;g=get_group(cid)
    if not g or not g['approved']:return
    if msg.sender_chat and cfg(cid)['channel_posts_delete']:
        # Telegram represents channel posts and anonymous/group-as-chat messages via sender_chat.
        # Only delete channel identities, not anonymous administrators posting as the group itself.
        if msg.sender_chat.type=='channel' and msg.sender_chat.id != cid:
            await safe_delete(context.bot,cid,msg.message_id)
            return
    if not msg.from_user:return
    d=cfg(cid);u=msg.from_user
    with conn() as c:
        c.execute('INSERT OR IGNORE INTO seen VALUES (?,?,?)',(cid,msg.message_id,int(time.time())));c.commit()
    if await authorized(context.bot,u.id,cid) or u.id in d['allowlist']:return
    text=(msg.text or msg.caption or '')
    if d['links']:
        entities=list(msg.entities or [])+list(msg.caption_entities or [])
        link=any(e.type in ('url','text_link') for e in entities) or bool(re.search(r'(?i)(https?://|www\.|t\.me/)',text))
        if link:
            await safe_delete(context.bot,cid,msg.message_id)
            await warning(context.bot,cid,u,'לא שולחים קישורים');return
    if d['words'] and any(w in text.lower() for w in d['words']):
        await safe_delete(context.bot,cid,msg.message_id)
        action=d['word_action']
        if action=='warn':await warning(context.bot,cid,u,'מילה אסורה')
        elif action=='mute':await mute(context.bot,cid,u,d['word_mute'],'מילה אסורה')
        elif action=='ban':
            try:await context.bot.ban_chat_member(cid,u.id)
            except TelegramError:log.exception('Ban failed')
        return
    if d['flood']:
        now=time.monotonic();key=(cid,u.id);dq=FLOODS[key];dq.append(now)
        while dq and dq[0]<now-d['flood_seconds']:dq.popleft()
        if len(dq)>d['flood_count']:
            await safe_delete(context.bot,cid,msg.message_id);dq.clear()
            await mute(context.bot,cid,u,d['flood_mute'],'הצפת הודעות');return
    for item in d['replies']:
        trigger=item['trigger'].casefold();body=text.casefold().strip()
        if (item['mode']=='exact' and body==trigger) or (item['mode']=='contains' and trigger in body):
            await send_formatted(context.bot,cid,item['text'],u,buttons(item.get('buttons')),item.get('media'),msg.message_id)
            break


async def commands(update,context):
    msg=update.message;cid=msg.chat_id;u=msg.from_user;cmd=msg.text.split()[0].split('@')[0].lower().lstrip('/')
    if not await authorized(context.bot,u.id,cid):return
    g=get_group(cid)
    if not g or not g['approved']:return
    await safe_delete(context.bot,cid,msg.message_id)
    target=msg.reply_to_message.from_user if msg.reply_to_message else None
    args=msg.text.split()[1:]
    if cmd in ('lock','unlock'):
        await change_lock(context.bot,cid,cmd=='lock','manual');return
    if cmd=='clean':
        n=min(100,max(1,int(args[0]) if args and args[0].isdigit() else 20))
        with conn() as c:
            ids=[r[0] for r in c.execute('SELECT mid FROM seen WHERE chat=? ORDER BY mid DESC LIMIT ?',(cid,n))]
        for mid in ids:await safe_delete(context.bot,cid,mid)
        return
    if cmd=='export':await export_file(context.bot,cid,cid);return
    if cmd=='import':
        doc=msg.reply_to_message.document if msg.reply_to_message else None
        if not doc or doc.file_size>1_000_000:
            await context.bot.send_message(cid,'השב לקובץ גיבוי JSON קטן מ־1MB עם /import');return
        try:
            f=await context.bot.get_file(doc.file_id);raw=await f.download_as_bytearray()
            data=json.loads(raw.decode('utf-8'))
            if data.get('format')!='cinemix-settings-v1' or not isinstance(data.get('settings'),dict):raise ValueError()
            clean={**copy.deepcopy(DEFAULT),**{k:v for k,v in data['settings'].items() if k in DEFAULT}}
            PENDING[('import',u.id,cid)]=clean
            await context.bot.send_message(cid,'⚠️ ייבוא זה יחליף את כל הגדרות הקבוצה. לא יועברו אישורי קבוצות.',reply_markup=kb([('✅ אישור ייבוא',f'import:x:{cid}')]))
        except Exception:await context.bot.send_message(cid,'❌ קובץ גיבוי לא תקין')
        return
    if cmd in ('allow','unallow') and target:
        d=cfg(cid);s=set(d['allowlist']);s.add(target.id) if cmd=='allow' else s.discard(target.id)
        d['allowlist']=list(s);save_cfg(cid,d);return
    if cmd=='unban' and args and args[0].lstrip('-').isdigit():
        try:await context.bot.unban_chat_member(cid,int(args[0]),only_if_banned=True)
        except TelegramError:pass
        return
    if not target:return
    if target.id==OWNER or await authorized(context.bot,target.id,cid):return
    if cmd in ('warn','mute','ban'):
        await safe_delete(context.bot,cid,msg.reply_to_message.message_id)
    if cmd=='warn':await warning(context.bot,cid,target,' '.join(args))
    elif cmd=='warnings':
        n=warn_count(cid,target.id)
        await context.bot.send_message(cid,f'⚠️ {mention(target)}: {n}/{cfg(cid)["max_warn"]}',parse_mode=ParseMode.HTML)
    elif cmd=='mute':
        sec=duration(args[0]) if args else None
        if sec:await mute(context.bot,cid,target,sec,' '.join(args[1:]))
    elif cmd=='unmute':
        try:await context.bot.restrict_chat_member(cid,target.id,permissions=await member_permissions(context.bot,cid))
        except TelegramError:pass
    elif cmd=='ban':
        try:
            await context.bot.ban_chat_member(cid,target.id)
            txt=f'🚫 המשתמש {mention(target)} הורחק מהקבוצה.'
            if args:txt+='\n📋 סיבה: '+html.escape(' '.join(args))
            await context.bot.send_message(cid,txt,parse_mode=ParseMode.HTML)
        except TelegramError:log.exception('Ban failed')


async def export_file(bot,recipient,cid):
    from io import BytesIO
    g=get_group(cid)
    data={'format':'cinemix-settings-v1','source':g['title'],'settings':cfg(cid)}
    bio=BytesIO(json.dumps(data,ensure_ascii=False,indent=2).encode());bio.name='CINEMIX_settings.json'
    await bot.send_document(recipient,bio,caption='📦 גיבוי הגדרות CINEMIX. אין בו טוקן או הרשאות בעלים.')


def permissions_to_dict(p):
    if not p:return {}
    fields=('can_send_messages','can_send_audios','can_send_documents','can_send_photos','can_send_videos','can_send_video_notes','can_send_voice_notes','can_send_polls','can_send_other_messages','can_add_web_page_previews','can_change_info','can_invite_users','can_pin_messages','can_manage_topics')
    return {k:getattr(p,k,None) for k in fields}


async def member_permissions(bot,cid):
    chat=await bot.get_chat(cid)
    return chat.permissions or ChatPermissions(can_send_messages=True)


async def change_lock(bot,cid,lock,reason):
    g=get_group(cid)
    if not g or not g['approved']:return
    d=cfg(cid)
    if lock and g['locked']:return
    if not lock and not g['locked']:return
    try:
        if lock:
            chat=await bot.get_chat(cid)
            original=permissions_to_dict(chat.permissions)
            await bot.set_chat_permissions(cid,ChatPermissions(can_send_messages=False,can_send_audios=False,can_send_documents=False,can_send_photos=False,can_send_videos=False,can_send_video_notes=False,can_send_voice_notes=False,can_send_polls=False,can_send_other_messages=False,can_add_web_page_previews=False))
            set_group(cid,locked=1,permissions=json.dumps(original),lock_reason=reason)
            key='holiday_lock_text' if reason=='holiday' else 'shabbat_lock_text' if reason=='shabbat' else 'lock_text'
        else:
            original=json.loads(g['permissions'] or '{}')
            await bot.set_chat_permissions(cid,ChatPermissions(**original))
            set_group(cid,locked=0,permissions=None,lock_reason=None)
            key='holiday_unlock_text' if g['lock_reason']=='holiday' else 'shabbat_unlock_text' if g['lock_reason']=='shabbat' else 'unlock_text'
        await send_formatted(bot,cid,d[key])
    except TelegramError:log.exception('Lock/unlock failed for %s',cid)


JERUSALEM = Observer(latitude=31.778, longitude=35.235, elevation=750)


def yom_tov(day):
    """Israeli Yom Tov days (not Chol Hamoed); civil date in Asia/Jerusalem."""
    h = dates.GregorianDate(day.year, day.month, day.day).to_heb()
    return ((h.month == 7 and h.day in (1, 2, 10, 15, 22)) or
            (h.month == 1 and h.day in (15, 21)) or
            (h.month == 3 and h.day == 6))


def shabbat(day):
    return day.weekday() == 5


def sunset_local(day):
    return sun(JERUSALEM, date=day, tzinfo=TZ)['sunset']


async def calendar_tick(bot, cid, group_row, settings, now):
    """Fixed Erev start time, Jerusalem sunset + configurable nightfall + wait.
    Sunset offset is an approximation, NOT a certified halachic zman.
    """
    today = now.date()
    tomorrow = today + timedelta(days=1)
    today_shabbat = settings['shabbat'] and shabbat(today)
    today_holiday = settings['holiday'] and yom_tov(today)
    next_shabbat = settings['shabbat'] and shabbat(tomorrow)
    next_holiday = settings['holiday'] and yom_tov(tomorrow)
    hm = now.strftime('%H:%M')
    # Lock on fixed Friday or Erev Yom Tov clock time; if process restarts
    # during the prohibited period, restore the lock when possible.
    start_friday = (today.weekday() == 4 and settings['shabbat'] and hm >= settings['friday_time'])
    start_holiday = next_holiday and hm >= settings['holiday_time']
    in_period = today_shabbat or today_holiday
    deadline = sunset_local(today) + timedelta(minutes=int(settings['nightfall_minutes']) + int(settings['end_offset']))
    scheduled = start_friday or start_holiday or (in_period and (next_shabbat or next_holiday or now < deadline))
    reason = 'holiday' if (today_holiday or start_holiday) else 'shabbat'
    if scheduled and not group_row['locked']:
        await change_lock(bot, cid, True, reason)
        return
    if not group_row['locked'] or group_row['lock_reason'] not in ('shabbat', 'holiday'):
        return
    # Keep the group locked across adjacent Yom Tov/Shabbat days.
    if next_shabbat or next_holiday:
        return
    if in_period:
        if now >= deadline:
            await change_lock(bot, cid, False, group_row['lock_reason'])
    elif not scheduled:
        # Recovery after an outage, when an earlier scheduled unlock was missed.
        await change_lock(bot, cid, False, group_row['lock_reason'])


async def periodic(context):
    now=datetime.now(TZ);stamp=int(now.timestamp())
    with conn() as c:
        expired=c.execute('SELECT chat,mid FROM welcomes WHERE expires>0 AND expires<=?',(stamp,)).fetchall()
    for item in expired:
        await safe_delete(context.bot,item['chat'],item['mid'])
        with conn() as c:c.execute('DELETE FROM welcomes WHERE chat=? AND mid=?',(item['chat'],item['mid']));c.commit()
    for g in all_groups():
        cid=g['id']
        if not g['approved']:continue
        d=cfg(cid)
        await calendar_tick(context.bot,cid,g,d,now)
        # Daily schedules, fixed Jerusalem local time. Prevent repeated execution in same minute.
        hm=now.strftime('%H:%M')
        if d['daily_lock'] and hm==d['daily_lock_time'] and not g['locked']:
            await change_lock(context.bot,cid,True,'manual')
        if d['daily_lock'] and hm==d['daily_unlock_time'] and g['locked'] and g['lock_reason']=='manual':
            await change_lock(context.bot,cid,False,'manual')
        if g['locked']:continue
        changed=False
        for item in d['announcements']:
            if stamp-int(item.get('last',0))>=int(item.get('minutes',60))*60:
                try:await send_formatted(context.bot,cid,item['text'],markup=buttons(item.get('buttons')),media=item.get('media'))
                except TelegramError:log.exception('Announcement send')
                item['last']=stamp;changed=True
        if changed:save_cfg(cid,d)



async def status_cmd(update,context):
    if update.effective_chat.type!='private' or update.effective_user.id!=OWNER:return
    groups=all_groups()
    with conn() as c:
        all_count=c.execute('SELECT COUNT(*) FROM groups').fetchone()[0]
    await update.message.reply_text(f'🩺 CINEMIX מצב מערכת\nקבוצות פעילות: {len(groups)}\nמאושרות ופעילות: {sum(bool(g["approved"]) for g in groups)}\nרשומות כולל קבוצות שהוסרו: {all_count}\nמסד נתונים: {DB}\n\nשים לב: אם מסד הנתונים אינו על דיסק קבוע, הנתונים עלולים להימחק בפריסה מחדש.')

async def private_document(update,context):
    # Document import is only accepted by replying /import in the target group.
    return


async def error_handler(update,context):
    log.error('Unhandled bot error: %s',context.error,exc_info=context.error)


def main():
    if not TOKEN:raise RuntimeError('Set BOT_TOKEN in Render environment variables')
    conn().close()
    app=ApplicationBuilder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.ChatType.GROUPS,track_group),group=-1)
    app.add_handler(CommandHandler('start',start))
    app.add_handler(CommandHandler('admin',owner_panel))
    app.add_handler(CommandHandler('setstart',set_start_text))
    app.add_handler(CommandHandler('showstart',show_start_text))
    app.add_handler(CommandHandler('status',status_cmd))
    app.add_handler(CommandHandler('manage',manage))
    app.add_handler(CommandHandler('register',register_group))
    app.add_handler(CommandHandler('groups',groups_cmd))
    app.add_handler(CommandHandler('cancel',cancel))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(ChatMemberHandler(my_member,ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (filters.TEXT|filters.PHOTO|filters.VIDEO) & ~filters.COMMAND,input_private))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.StatusUpdate.NEW_CHAT_MEMBERS,new_members))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & (filters.StatusUpdate.LEFT_CHAT_MEMBER|filters.StatusUpdate.NEW_CHAT_TITLE|filters.StatusUpdate.NEW_CHAT_PHOTO|filters.StatusUpdate.DELETE_CHAT_PHOTO|filters.StatusUpdate.PINNED_MESSAGE),service))
    group_commands=['warn','warnings','mute','unmute','ban','unban','clean','lock','unlock','allow','unallow','export','import']
    for command in group_commands:app.add_handler(CommandHandler(command,commands,filters=filters.ChatType.GROUPS))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND & ~filters.StatusUpdate.ALL,moderate))
    app.add_error_handler(error_handler)
    if app.job_queue:app.job_queue.run_repeating(periodic,interval=60,first=15)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__=='__main__':main()
