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
OWNER = int(os.getenv('OWNER_ID', '0'))
DB = os.getenv('DB_PATH', 'cinemix_groups.sqlite3')
TZ = ZoneInfo('Asia/Jerusalem')
FLOODS = defaultdict(deque)
PENDING = {}
LAST_WELCOME = {}

DEFAULT = {
 'links': True, 'max_warn': 3, 'delete_slash_commands': True, 'welcome': True, 'welcome_text': '👋 ברוך הבא {user}!\nשמחים שהצטרפת אלינו 💜',
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
  'stealth': False, 'forward_filter': 'allow', 'rules_text': '', 'rules_welcome_button': False,
  'trusted': [], 'milestones': False, 'milestone_step': 100, 'milestone_text': '🎉 הגענו ל־{count} חברים!',
}
HELP = {
 'links': '🔗 חסימת קישורים: קישור של משתמש רגיל נמחק והוא מקבל אזהרה. בהגעה למכסה הוא מורחק. מנהלים ומשתמשים מורשים מוחרגים. /warn בתגובה להודעה מוסיף אזהרה ידנית.',
 'welcome': '👋 ברוכים הבאים: הגדירו טקסט, כפתורים, תמונה/וידאו וזמן מחיקה. ההודעה החדשה מחליפה את הקודמת. {user} יוצר תיוג לחיץ.',
 'flood': '🛡️ אנטי ספאם: בחרו מספר הודעות, חלון זמן ומשך השתקה בשניות. עודף הודעות נמחק וגורר השתקה.',
 'words': '🚫 מילים אסורות: הגדירו רשימה מופרדת בפסיקים ובחרו פעולה: delete / warn / mute / ban.',
 'lock': '🔒 נעילה: שומרת את הרשאות ברירת המחדל של הקבוצה ומחזירה אותן בפתיחה. /lock ו-/unlock בקבוצה. להפעלה יומית לחצו על 🔴 נעילה יומית: כבויה כדי להפוך ל־🟢 פעילה, והגדירו שעות נעילה ופתיחה לפי שעון ישראל (כולל אחרי חצות).',
 'calendar': '🕯️ שבת וחג: נעילה בשעה קבועה ביום שישי או בערב חג לפי לוח ישראל. פתיחה לפי שקיעה בירושלים + דקות לצאת משוער + דקות המתנה. זהו חישוב משוער ולא זמן הלכתי מוסמך; יש לוודא התאמה למנהג הקבוצה. שבת וחג רצופים נשארים נעולים.',
 'users': '👮 ניהול משתמשים: הגיבו להודעה עם /warn [סיבה], /mute 30m [סיבה], /unmute, /ban [סיבה], /unban (לפי מזהה). /warnings בתגובה מציג אזהרות. /clean 50 מוחק הודעות אחרונות שנצפו.',
 'replies': '🤖 תגובות: הגדירו טריגר, מצב exact או contains, טקסט וכפתורים. ההודעה המקורית והתגובה נשארות.',
 'announcements': '📢 הודעות אוטומטיות: לחץ על ״הוספת פרסום אוטומטי מודרך״, הגדר מרווח בדקות (למשל 180 = 3 שעות), הזן הודעה ואשר. דרך הרשימה אפשר לערוך, למחוק, להשהות ולהגדיר מחיקת הודעה קודמת. בזמן נעילה הפרסומים מושהים.',
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
    c.execute('CREATE TABLE IF NOT EXISTS invitations (chat INTEGER PRIMARY KEY, inviter INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS stats (chat INTEGER, kind TEXT, amount INTEGER DEFAULT 0, PRIMARY KEY(chat,kind))')
    c.execute('CREATE TABLE IF NOT EXISTS drafts (uid INTEGER PRIMARY KEY, chat INTEGER, kind TEXT, payload TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS group_requests (chat INTEGER PRIMARY KEY, notified INTEGER DEFAULT 0, requested_at INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, chat INTEGER, actor INTEGER, action TEXT, detail TEXT, created INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS owner_backups (id INTEGER PRIMARY KEY AUTOINCREMENT, created INTEGER, payload TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS member_counts (chat INTEGER PRIMARY KEY, last_count INTEGER DEFAULT 0)')
    c.execute('CREATE TABLE IF NOT EXISTS admin_panels (uid INTEGER PRIMARY KEY, chat INTEGER, mid INTEGER)')
    c.commit()
    return c


def meta_get(key, default=''):
    with conn() as c:
        row=c.execute('SELECT val FROM meta WHERE key=?',(key,)).fetchone()
    return row['val'] if row else default


def meta_set(key,value):
    with conn() as c:
        c.execute('INSERT OR REPLACE INTO meta(key,val) VALUES (?,?)',(key,str(value)))
        c.commit()


def audit(cid,uid,action,detail=''):
    with conn() as c:
        c.execute('INSERT INTO audit(chat,actor,action,detail,created) VALUES (?,?,?,?,?)',(cid,uid,action,str(detail)[:500],int(time.time())))
        c.commit()


def approved_groups():
    return [g for g in all_groups() if g['approved'] and g['active']]


def backup_payload():
    with conn() as c:
        groups=[dict(r) for r in c.execute('SELECT * FROM groups')]
        warnings=[dict(r) for r in c.execute('SELECT * FROM warnings')]
    return {'format':'cinemix-owner-backup-v1','created':int(time.time()),'groups':groups,'warnings':warnings}


def backup_save():
    data=backup_payload()
    with conn() as c:
        c.execute('INSERT INTO owner_backups(created,payload) VALUES (?,?)',(data['created'],json.dumps(data,ensure_ascii=False)))
        c.execute('DELETE FROM owner_backups WHERE id NOT IN (SELECT id FROM owner_backups ORDER BY id DESC LIMIT 30)')
        c.commit()
    return data


def restore_backup(data):
    if not isinstance(data,dict) or data.get('format')!='cinemix-owner-backup-v1':raise ValueError('Invalid backup')
    groups=data.get('groups');warnings=data.get('warnings')
    if not isinstance(groups,list) or not isinstance(warnings,list):raise ValueError('Invalid backup contents')
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('DELETE FROM groups');c.execute('DELETE FROM warnings')
        for g in groups:
            cols=('id','title','approved','settings','locked','permissions','lock_reason','last_announcement','active')
            c.execute('INSERT INTO groups ('+','.join(cols)+') VALUES ('+','.join('?' for _ in cols)+')',tuple(g.get(k) for k in cols))
        for w in warnings:c.execute('INSERT INTO warnings(chat,uid,count) VALUES (?,?,?)',(w['chat'],w['uid'],w['count']))
        c.commit()


async def owner_notify(bot, text, to_groups=True, to_admins=True):
    successes=0;failures=0;seen=set()
    for group in approved_groups():
        cid=group['id']
        if to_groups:
            try:await bot.send_message(cid,text);successes+=1
            except TelegramError:failures+=1
        if to_admins:
            try:
                admins=await bot.get_chat_administrators(cid)
                for adm in admins:
                    user=adm.user
                    if user.is_bot or user.id in seen:continue
                    seen.add(user.id)
                    try:await bot.send_message(user.id,text);successes+=1
                    except TelegramError:failures+=1
            except TelegramError:failures+=1
        await asyncio.sleep(0.1)
    return successes,failures


def metric(cid,kind,n=1):
    with conn() as c:
        c.execute('INSERT INTO stats(chat,kind,amount) VALUES (?,?,?) ON CONFLICT(chat,kind) DO UPDATE SET amount=amount+excluded.amount',(cid,kind,n))
        c.commit()


def draft_set(uid,cid,kind,payload):
    with conn() as c:
        c.execute('INSERT OR REPLACE INTO drafts(uid,chat,kind,payload) VALUES (?,?,?,?)',(uid,cid,kind,json.dumps(payload,ensure_ascii=False)));c.commit()


def draft_get(uid):
    with conn() as c:r=c.execute('SELECT * FROM drafts WHERE uid=?',(uid,)).fetchone()
    return (r['chat'],r['kind'],json.loads(r['payload'])) if r else None


def draft_clear(uid):
    with conn() as c:c.execute('DELETE FROM drafts WHERE uid=?',(uid,));c.commit()


def pending_set(uid,cid,key):
    with conn() as c:c.execute('INSERT OR REPLACE INTO pending_edits(uid,chat,field) VALUES (?,?,?)',(uid,cid,key));c.commit()


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


def message_formatted(msg):
    """Preserve Telegram bold, italic, underline, links and other entities safely."""
    if msg.text is not None:
        return 'HTML:' + msg.text_html if msg.entities else msg.text
    if msg.caption is not None:
        return 'HTML:' + msg.caption_html if msg.caption_entities else msg.caption
    return ''


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
    """Send one owner approval request per pending group, retry if delivery fails."""
    g=get_group(cid)
    if not g or g['approved'] or not g['active']:
        return False
    with conn() as c:
        row=c.execute('SELECT notified FROM group_requests WHERE chat=?',(cid,)).fetchone()
        if row and row['notified']:
            return False
        c.execute('INSERT OR IGNORE INTO group_requests(chat,notified,requested_at) VALUES (?,0,?)',(cid,int(time.time())))
        c.commit()
    with conn() as c:
        invitation=c.execute('SELECT inviter FROM invitations WHERE chat=?',(cid,)).fetchone()
    who=f"\nמבקש: {invitation['inviter']}" if invitation else ''
    try:
        await bot.send_message(OWNER,f'📥 בקשת אישור חדשה\n{g["title"]}\nID: {cid}{who}',reply_markup=kb([('✅ אישור',f'approval:1:{cid}'),('❌ דחייה',f'approval:0:{cid}')]))
    except TelegramError:
        log.exception('Owner notification failed for group %s',cid)
        return False
    with conn() as c:
        c.execute('UPDATE group_requests SET notified=1 WHERE chat=?',(cid,))
        c.commit()
    return True


async def request_group_approval(bot,chat,inviter=None,force=False):
    """Register and request approval, without exposing management before approval."""
    g=get_group(chat.id)
    if not g:
        upsert(chat.id,chat.title or str(chat.id))
        g=get_group(chat.id)
    if inviter:
        with conn() as c:
            c.execute('INSERT OR IGNORE INTO invitations(chat,inviter) VALUES (?,?)',(chat.id,inviter))
            c.commit()
    if g['approved']:
        return 'approved'
    if force:
        # A manual /register repairs a missed owner notification from older builds.
        with conn() as c:
            c.execute('INSERT OR IGNORE INTO group_requests(chat,notified,requested_at) VALUES (?,0,?)',(chat.id,int(time.time())))
            c.commit()
    sent=await notify_owner(bot,chat.id)
    if sent:
        return 'sent'
    with conn() as c:
        row=c.execute('SELECT notified FROM group_requests WHERE chat=?',(chat.id,)).fetchone()
    return 'pending' if row and row['notified'] else 'failed'


async def my_member(update,context):
    ev=update.my_chat_member
    if not ev or ev.chat.type not in ('group','supergroup'):
        return
    before=ev.old_chat_member.status
    after=ev.new_chat_member.status
    active=(ChatMemberStatus.MEMBER,ChatMemberStatus.ADMINISTRATOR,ChatMemberStatus.OWNER)
    if after in active:
        if before not in active:
            old=get_group(ev.chat.id)
            if not old:
                upsert(ev.chat.id,ev.chat.title or str(ev.chat.id))
            else:
                upsert(ev.chat.id,ev.chat.title or str(ev.chat.id))
            result=await request_group_approval(context.bot,ev.chat,ev.from_user.id if ev.from_user else None)
            if result!='approved':
                message='✅ הבקשה נשלחה לבעלים לאישור.' if result in ('sent','pending') else '⚠️ לא הצלחנו להעביר את הבקשה לבעלים. נסו /register.'
                try:await context.bot.send_message(ev.chat.id,message)
                except TelegramError:log.exception('Cannot send group request confirmation')
        elif not get_group(ev.chat.id):
            result=await request_group_approval(context.bot,ev.chat,ev.from_user.id if ev.from_user else None)
            if result!='approved':
                try:await context.bot.send_message(ev.chat.id,'✅ הבקשה נשלחה לבעלים לאישור.' if result!='failed' else '⚠️ הבקשה לא הועברה לבעלים.')
                except TelegramError:pass
    elif after in (ChatMemberStatus.LEFT,ChatMemberStatus.BANNED) and before in active:
        set_group(ev.chat.id,active=0)
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
               [('🗑️ מחיקת פקודות',f'page:command_cleanup:{cid}')],
              [('📣 פרסום עכשיו',f'wiz:broadcast:{cid}'),('📊 סטטיסטיקות',f'stats:x:{cid}')],
              [('🩺 בדיקת הרשאות',f'health:x:{cid}'),('👑 פאנל בעלים',f'ownerall:x:{cid}')],
              [('🕵️ מנהל סמוי',f'page:stealth:{cid}'),('🧪 סימולטור',f'page:simulator:{cid}')],
               [('📜 חוקי קבוצה',f'page:rules:{cid}'),('🔄 הודעות מועברות',f'page:forward:{cid}')],
               [('📋 יומן פעולות',f'page:audit:{cid}'),('⭐ משתמשים מהימנים',f'page:trusted:{cid}')],
               [('📖 מדריך',f'page:guide:{cid}'),('⬅️ קבוצות',f'list:all:0')])


async def list_groups(bot,uid,cid):
    groups=[]
    for g in all_groups():
        if uid==OWNER or (g['approved'] and await authorized(bot,uid,g['id'])):groups.append(g)
    if not groups:
        await panel_update(bot,uid,'אין כרגע קבוצות זמינות לניהול.',kb([('⬅️ חזרה','owner:overview:0')]) if uid==OWNER else None)
        return
    rows=[]
    for g in groups[:70]:
        rows.append([('⚙️ '+g['title'][:45],f'open:x:{g["id"]}')])
        if uid==OWNER:rows.append([('❌ ביטול אישור' if g['approved'] else '✅ אישור',f'approval:{0 if g["approved"] else 1}:{g["id"]}')])
    if uid==OWNER:rows.append([('⬅️ חזרה לפאנל הבעלים','owner:overview:0')])
    await panel_update(bot,uid,'👥 קבוצות לניהול — בחר קבוצה:',kb(*rows))


def regular_start_text():
    with conn() as c:
        r=c.execute("SELECT val FROM meta WHERE key='regular_start_text'").fetchone()
    return r['val'] if r else system_text('owner_welcome')


# Owner-managed explanations. Missing overrides retain the original wording.
EXPLANATION_LABELS = {
    'links':'🔗 קישורים', 'welcome':'👋 ברוכים הבאים', 'flood':'🛡️ אנטי ספאם',
    'words':'🚫 מילים אסורות', 'lock':'🔒 נעילה', 'calendar':'🕯️ שבת וחג',
    'users':'👮 משתמשים', 'replies':'🤖 תגובות', 'announcements':'📢 הודעות חוזרות',
    'verify':'✅ אימות', 'backup':'📦 גיבוי', 'channels':'📣 הודעות ערוץ',
    'allowlist':'🛡️ מורשים', 'stealth':'🕵️ מנהל סמוי',
    'forward':'🔄 הודעות מועברות', 'trusted':'⭐ משתמשים מהימנים',
    'service':'🗑️ הודעות שירות', 'rules':'📜 חוקי קבוצה', 'audit':'📋 יומן פעולות',
    'simulator':'🧪 סימולטור', 'guide':'📖 מדריך', 'command_cleanup':'🗑️ מחיקת פקודות',
}
EXPLANATION_SPECIAL = {
    'stealth': ('🕵️ מצב מנהל סמוי\n\nכדי לענות בשם הבוט: הגב להודעת המשתמש בקבוצה עם /reply, '
                'ואז שלח את התשובה לבוט בפרטי.\n\nפקודות: /warn, /mute 30m, /ban, /unmute.'),
    'forward': '🔄 סינון הודעות מועברות: allow = מותר; channels = מערוצים; all = הכול.',
    'trusted': '⭐ משתמשים מהימנים: /allow בתגובה להודעה, /unallow להסרה.',
}

# The original short texts are retained even if older detailed overrides exist.
SHORT_DEFAULTS = {**HELP, **EXPLANATION_SPECIAL,
    'service':'🗑️ מחיקת הודעות שירות בקבוצה.',
    'rules':'📜 חוקי הקבוצה והאפשרות לפרסם אותם.',
    'audit':'📋 צפייה בפעולות ניהול אחרונות.',
    'simulator':'🧪 בדיקת תגובת הבוט להודעה.',
    'guide':'📖 מדריך השימוש של CINEMIX.',
    'command_cleanup':'🗑️ מחיקה אוטומטית של הודעות שמתחילות ב־/ בקבוצה.',
}
DETAIL_DEFAULTS = {**SHORT_DEFAULTS,
    'command_cleanup':'🗑️ מחיקת פקודות: כשהאפשרות פעילה, הודעות שמתחילות ב־/ נמחקות מהקבוצה, גם ממשתמשים רגילים. פקודות מורשות ממשיכות להתבצע. נדרשת הרשאת מחיקת הודעות.',
}
SYSTEM_TEXTS = {
    'owner_welcome':'🛡️ ברוכים הבאים לבוט CINEMIX לניהול קבוצות!',
    'group_approved':'✅ הקבוצה אושרה להפעלת CINEMIX. מנהלי הקבוצה יכולים כעת לפתוח ניהול בפרטי.',
    'group_rejected':'❌ הקבוצה לא אושרה לשימוש ב-CINEMIX. הבוט לא יבצע פעולות ניהול בקבוצה.',
    'approval_sent':'✅ הבקשה נשלחה לבעלים לאישור.',
    'approval_failed':'⚠️ הבקשה לא הועברה לבעלים. נסו שוב מאוחר יותר.',
    'maintenance_notice':'🛠️ הבוט נמצא כעת בתחזוקה. אפשרויות הניהול זמנית אינן זמינות.',
    'maintenance_end':'✅ תחזוקת CINEMIX הסתיימה. אפשרויות הניהול חזרו לפעילות.',
    'import_invalid':'❌ קובץ גיבוי לא תקין',
    'import_prompt':'השב לקובץ גיבוי JSON קטן מ־1MB עם /import',
    'stealth_disabled':'🕵️ הפעל תחילה מצב מנהל סמוי בפאנל הקבוצה.',
    'stealth_prompt':'💬 שלח כאן את התשובה שלך. היא תפורסם בקבוצה כתגובה להודעה המקורית, בשם הבוט. /cancel לביטול.',
}
SYSTEM_LABELS = {
    'owner_welcome':'הודעת פתיחה כללית', 'group_approved':'אישור קבוצה',
    'group_rejected':'דחיית קבוצה', 'approval_sent':'בקשת אישור נשלחה',
    'approval_failed':'שגיאת בקשת אישור', 'maintenance_notice':'הודעת תחזוקה',
    'maintenance_end':'סיום תחזוקה', 'import_invalid':'גיבוי לא תקין',
    'import_prompt':'הנחיית ייבוא', 'stealth_disabled':'מנהל סמוי כבוי',
    'stealth_prompt':'הנחיית תגובה סמויה',
}

def editable_text(kind,key):
    defaults={'short':SHORT_DEFAULTS,'detail':DETAIL_DEFAULTS,'system':SYSTEM_TEXTS}[kind]
    if kind=='detail':
        # Compatibility with owner explanation edits from the preceding release.
        old=meta_get('explanation_override:'+key,'')
        return meta_get('owner_text:detail:'+key,'') or old or defaults.get(key,'')
    return meta_get('owner_text:'+kind+':'+key,'') or defaults.get(key,'')

def explanation_text(key):
    return editable_text('detail',key)

def system_text(key):
    return editable_text('system',key)

def explanation_picker():
    rows=[[ (EXPLANATION_LABELS[k],f'ownerexplain:select:{k}') ] for k in EXPLANATION_LABELS]
    rows.append([('💬 תגובות והודעות מערכת','ownerexplain:systems:0')])
    rows.append([('⬅️ חזרה לפאנל הבעלים','owner:overview:0')])
    return kb(*rows)

def owner_text_actions(kind,key):
    label=SYSTEM_LABELS.get(key,key) if kind=='system' else EXPLANATION_LABELS[key]
    text=editable_text(kind,key)
    heading={'short':'הסבר קצר','detail':'הסבר שימוש מפורט','system':'הודעת מערכת'}[kind]
    return ('📝 '+label+' — '+heading+'\n\n'+text[:3300],
        kb([('✏️ עריכת הטקסט',f'ownertext:edit:{kind},{key}')],
           [('🔄 חזרה לברירת מחדל',f'ownertext:reset:{kind},{key}')],
           [('⬅️ חזרה',f'ownerexplain:{"systems" if kind=="system" else "select"}:{"0" if kind=="system" else key}')]))

def owner_menu():
    return kb(
        [('📊 תמונת מצב', 'owner:overview:0'),('👥 כל הקבוצות','list:all:0')],
        [('📥 בקשות ממתינות','owner:pending:0'),('🩺 בריאות קבוצות','owner:health:0')],
        [('📣 פרסום מרכזי','owner:broadcast:0'),('📈 פעילות מערכת','owner:metrics:0')],
        [('📝 הודעת פתיחה','owner:start:0'),('⚙️ הגדרות מערכת','owner:settings:0')],
        [('💾 גיבויים','owner:backups:0'),('🛠️ תחזוקה','owner:maintenance:0')],
         [('📝 ניהול הסברים והודעות מערכת','owner:explanations:0')],
         [('📖 מדריך','guide:all:0')])


async def owner_dashboard(bot,recipient,section):
    groups=all_groups()
    approved=[g for g in groups if g['approved']]
    pending=[g for g in groups if not g['approved'] and g['active']]
    active=[g for g in approved if g['active']]
    if section=='overview':
        with conn() as c:
            total=c.execute('SELECT COALESCE(SUM(amount),0) FROM stats').fetchone()[0]
            requests=c.execute('SELECT COUNT(*) FROM invitations').fetchone()[0]
        msg=(f'👑 CINEMIX — תמונת מצב\n\n👥 קבוצות במערכת: {len(groups)}\n'
             f'✅ מאושרות: {len(approved)}\n🟢 פעילות: {len(active)}\n'
             f'⏳ ממתינות: {len(pending)}\n📥 הזמנות שתועדו: {requests}\n'
             f'📊 פעולות שנמדדו: {total}\n\nכל קבוצה שומרת הגדרות עצמאיות.')
    elif section=='pending':
        msg='📥 בקשות ממתינות\n' + ('\n'.join(f'• {g["title"]} ({g["id"]})' for g in pending) if pending else 'אין בקשות ממתינות.')
    elif section=='health':
        lines=[]
        for g in active[:35]:
            try:
                me=await bot.get_me();m=await bot.get_chat_member(g['id'],me.id)
                missing=[]
                if m.status!='administrator':missing.append('לא מנהל')
                if not getattr(m,'can_delete_messages',False):missing.append('מחיקת הודעות')
                if not getattr(m,'can_restrict_members',False):missing.append('חסימה/השתקה')
                lines.append(('✅ ' if not missing else '⚠️ ')+g['title'][:35]+(': '+', '.join(missing) if missing else ': תקין'))
            except TelegramError:lines.append('❌ '+g['title'][:35]+': אין גישה')
        msg='🩺 בריאות קבוצות (עד 35)\n'+('\n'.join(lines) if lines else 'אין קבוצות פעילות.')
    elif section=='metrics':
        with conn() as c:
            rows=c.execute('SELECT kind,SUM(amount) AS total FROM stats GROUP BY kind ORDER BY total DESC LIMIT 20').fetchall()
        msg='📈 פעילות המערכת\n'+('\n'.join(f'• {r["kind"]}: {r["total"]}' for r in rows) if rows else 'אין עדיין פעולות שנמדדו.')
    elif section=='backups':
        with conn() as c: rows=c.execute('SELECT id,created FROM owner_backups ORDER BY id DESC LIMIT 8').fetchall()
        msg='💾 גיבויי בעלים\n'+('\n'.join(f'#{r["id"]} — {datetime.fromtimestamp(r["created"],TZ):%d/%m/%Y %H:%M}' for r in rows) if rows else 'אין עדיין גיבויים.')
        await panel_update(bot,recipient,msg,reply_markup=kb([('📦 צור גיבוי','ownerbackup:create:0')],[('📥 שחזור גיבוי אחרון','ownerbackup:restore:0')],[('⬅️ חזרה','owner:overview:0')]))
        return
    elif section=='maintenance':
        active=meta_get('maintenance','0')=='1'
        msg=f'🛠️ מצב תחזוקה: {"פעיל" if active else "כבוי"}\n\nבעת תחזוקה מנהלים לא יכולים לשנות הגדרות. ההגנות ונעילות הקבוצות ממשיכות לפעול.\nהודעת התחזוקה נשלחת לקבוצות המאושרות ולמנהלים שניתן לפנות אליהם בפרטי.'
        await panel_update(bot,recipient,msg,reply_markup=kb([('🟢 הפעל תחזוקה' if not active else '🔴 סיים תחזוקה','ownermaintenance:toggle:0')],[('✏️ ערוך הודעת תחזוקה','ownermaintenance:text:0')],[('⬅️ חזרה','owner:overview:0')]))
        return
    elif section=='explanations':
        await panel_update(bot,recipient,'📝 ניהול הסברים והודעות מערכת\n\nבחר הסבר לעריכה. כל הסבר שלא שינית נשאר בנוסח המקורי.',reply_markup=explanation_picker())
        return
    elif section=='start':
        msg='📝 הודעת הפתיחה הנוכחית:\n\n'+regular_start_text()[:2500]+'\n\nלשינוי: /setstart'
    elif section=='settings':
        msg=('⚙️ הגדרות מערכת — לבעלים בלבד\n\n'
             '• /setstart — שינוי הודעת פתיחה\n'
             '• /showstart — הצגת ההודעה\n'
             '• /groups — ניהול ואישור קבוצות\n'
             '• /admin — פאנל הבעלים\n\n'
             'גיבוי קבוצתי, הודעות חוזרות ויתר ההגדרות נמצאים בתוך ניהול הקבוצה. '
             'לא מתבצע שינוי גורף בהגדרות הקבוצות ללא אישור מפורש.')
    else:return
    await panel_update(bot,recipient,msg[:3900],reply_markup=kb([('⬅️ חזרה לפאנל הבעלים','owner:overview:0')]) if section!='overview' else owner_menu())


async def owner_panel(update,context):
    if update.effective_chat.type!='private' or update.effective_user.id!=OWNER:
        return
    await panel_new(context.bot,update.effective_user.id)
    await owner_dashboard(context.bot,update.effective_chat.id,'overview')


async def set_start_text(update,context):
    if update.effective_chat.type!='private' or update.effective_user.id!=OWNER:return
    value=update.message.text.partition(' ')[2].strip()
    if not value:
        with conn() as c:
            c.execute("INSERT OR REPLACE INTO pending_edits(uid,chat,field) VALUES (?,0,'owner_start_text')",(OWNER,));c.commit()
        await panel_update(context.bot,OWNER,'✏️ שלח עכשיו בהודעה רגילה את טקסט הפתיחה למשתמשים. /cancel לביטול.')
        return
    if len(value)>3500:
        await panel_update(context.bot,OWNER,'הטקסט ארוך מדי (עד 3500 תווים).')
        return
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO meta(key,val) VALUES ('regular_start_text',?)",(value,));c.commit()
    await panel_update(context.bot,OWNER,'✅ הודעת הפתיחה עודכנה.')


async def show_start_text(update,context):
    if update.effective_chat.type!='private' or update.effective_user.id!=OWNER:return
    await panel_update(context.bot,OWNER,regular_start_text())


async def start(update,context):
    if update.effective_chat.type!='private':return
    if update.effective_user.id==OWNER:
        await owner_panel(update,context)
    else:
        # Ordinary users only see the owner's welcome message, not management menus.
        with conn() as c:
            r=c.execute('SELECT COUNT(*) FROM invitations i JOIN groups g ON g.id=i.chat WHERE i.inviter=? AND g.approved=0 AND g.active=1',(update.effective_user.id,)).fetchone()
        await update.message.reply_text('✅ הבקשה נשלחה לבעלים לאישור.' if r[0] else regular_start_text())


async def manage(update,context):
    chat=update.effective_chat;uid=update.effective_user.id
    if chat.type!='private':
        if not await authorized(context.bot,uid,chat.id):return
        g=get_group(chat.id)
        if not g or not g['approved']:
            result=await request_group_approval(context.bot,chat,uid,force=True)
            await context.bot.send_message(chat.id,'✅ הבקשה נשלחה לבעלים לאישור.' if result!='failed' else '⚠️ הבקשה לא הועברה לבעלים. נסו שוב מאוחר יותר.')
            return
        await safe_delete(context.bot,chat.id,update.message.message_id)
        try:
            await panel_new(context.bot,uid)
            await panel_update(context.bot,uid,'⚙️ ניהול קבוצות:',reply_markup=kb([('👥 בחר קבוצה','list:all:0')]))
        except TelegramError:await context.bot.send_message(chat.id,'פתח תחילה את הבוט בפרטי ולחץ Start.')
    else:
        if uid==OWNER or any(g['approved'] and await authorized(context.bot,uid,g['id']) for g in all_groups()):
            await panel_new(context.bot,uid)
            await list_groups(context.bot,uid,chat.id)
        else:
            await panel_update(context.bot,OWNER,regular_start_text())


async def groups_cmd(update,context):
    if update.effective_chat.type=='private' and update.effective_user.id==OWNER:
        await panel_new(context.bot,OWNER)
        await list_groups(context.bot,OWNER,update.effective_chat.id)


async def track_group(update,context):
    # Do not silently register groups here: doing so before MY_CHAT_MEMBER
    # suppresses the owner approval request for a newly added bot.
    return


async def register_group(update,context):
    chat=update.effective_chat
    if chat.type not in ('group','supergroup'):
        return
    user=update.effective_user
    if not user or not await authorized(context.bot,user.id,chat.id):
        return
    result=await request_group_approval(context.bot,chat,user.id,force=True)
    if result=='approved':
        text='✅ הקבוצה כבר מאושרת במערכת.'
    elif result=='failed':
        text='⚠️ לא הצלחנו להעביר את הבקשה לבעלים. בדקו שהבעלים פתח את הבוט בפרטי ונסו שוב.'
    else:
        text='✅ הבקשה נשלחה לבעלים לאישור.'
    await context.bot.send_message(chat.id,text)


def panel_remember(uid,chat,mid):
    with conn() as c:
        c.execute('INSERT OR REPLACE INTO admin_panels(uid,chat,mid) VALUES (?,?,?)',(uid,chat,mid));c.commit()


def panel_location(uid):
    with conn() as c:r=c.execute('SELECT chat,mid FROM admin_panels WHERE uid=?',(uid,)).fetchone()
    return (r['chat'],r['mid']) if r else None


async def panel_new(bot,uid):
    """A fresh command starts a new panel below the command; button presses edit it."""
    with conn() as c:
        c.execute('DELETE FROM admin_panels WHERE uid=?',(uid,))
        c.commit()


async def panel_update(bot,uid,text,reply_markup=None):
    loc=panel_location(uid)
    if loc:
        try:
            await bot.edit_message_text(chat_id=loc[0],message_id=loc[1],text=str(text)[:4096],reply_markup=reply_markup)
            return
        except TelegramError as e:
            if 'not modified' in str(e).lower():return
            log.warning('Panel edit failed: %s',e)
    msg=await bot.send_message(uid,str(text)[:4096],reply_markup=reply_markup)
    panel_remember(uid,msg.chat_id,msg.message_id)


async def panel_from_query(q,text,reply_markup=None,**kwargs):
    await panel_update(q.get_bot(),q.from_user.id,text,reply_markup)


async def panel_from_input(update,context,text,reply_markup=None,**kwargs):
    await panel_update(context.bot,update.effective_user.id,text,reply_markup)


async def panel_input_handler(update,context):
    # Keep the administrator's original text/media in private chat for later reuse.
    # Only the bot's menu message is edited in place.
    await input_private(update,context)


async def panel_skip_handler(update,context):
    await skip(update,context)


def broadcast_picker(payload):
    rows=[]
    for group in all_groups():
        if group['approved']:
            selected=group['id'] in payload.get('targets',[])
            rows.append([(('☑️ ' if selected else '⬜ ')+group['title'][:35],f'broadcastpick:{group["id"]}:{payload["source"]}')])
    rows.append([('✅ סיום בחירה',f'broadcastpick:done:{payload["source"]}')])
    return kb(*rows)


# Navigation: actions refresh their current submenu; only Back navigates upward.
FIELD_PAGES = {
    'links':'links','max_warn':'links','welcome':'welcome','welcome_text':'welcome',
    'welcome_buttons':'welcome','welcome_media':'welcome','welcome_seconds':'welcome',
    'flood':'flood','flood_count':'flood','flood_seconds':'flood','flood_mute':'flood',
    'words':'words','word_action':'words','word_mute':'words',
    'daily_lock':'lock','daily_lock_time':'lock','daily_unlock_time':'lock',
    'lock_text':'lock','unlock_text':'lock',
    'shabbat':'calendar','holiday':'calendar','friday_time':'calendar',
    'holiday_time':'calendar','end_offset':'calendar','nightfall_minutes':'calendar',
    'shabbat_lock_text':'calendar','shabbat_unlock_text':'calendar',
    'holiday_lock_text':'calendar','holiday_unlock_text':'calendar',
    'verify':'verify','service_delete':'service','channel_posts_delete':'channels',
    'stealth':'stealth','forward_filter':'forward','rules_text':'rules',
    'delete_slash_commands':'command_cleanup',
}

def settings_page_text(page):
    if page in EXPLANATION_LABELS:
        return editable_text('short',page)
    return HELP.get(page,'⚙️ הגדרות הקבוצה — בחר פעולה:')

async def refresh_settings(query,cid,page,notice=''):
    text=(notice+'\n\n' if notice else '')+settings_page_text(page)
    markup=page_keyboard(cid,page)
    try:
        await query.edit_message_text(text[:3900],reply_markup=markup)
    except TelegramError as exc:
        if 'Message is not modified' not in str(exc):
            await panel_update(query.get_bot(),query.from_user.id,text[:3900],markup)

async def private_settings_result(message,cid,page,notice='✅ נשמר בהצלחה!'):
    await panel_update(message.get_bot(),message.from_user.id,notice+'\n\n'+settings_page_text(page),page_keyboard(cid,page))

def page_keyboard(cid,page):
    d=cfg(cid)
    toggles={'links':'links','welcome':'welcome','flood':'flood','verify':'verify','service':'service_delete','calendar':'shabbat','channels':'channel_posts_delete'}
    rows=[]
    if page in toggles:
        key=toggles[page];rows.append([('🟢 פעיל' if d[key] else '🔴 כבוי',f'toggle:{key}:{cid}')])
    if page=='stealth':rows.append([('🟢 מצב סמוי פעיל' if d['stealth'] else '🔴 מצב סמוי כבוי',f'toggle:stealth:{cid}')])
    if page=='forward':rows.append([('🔄 מצב: '+d['forward_filter'],f'cycle:forward_filter:{cid}')])
    if page=='rules':rows.extend([[('✏️ עריכת חוקי קבוצה',f'edit:rules_text:{cid}')],[('📢 פרסום החוקים',f'rulespublish:x:{cid}')]])
    if page=='simulator':rows.append([('🧪 שלח הודעה לבדיקה',f'simstart:x:{cid}')])
    if page=='audit':rows.append([('📋 20 פעולות אחרונות',f'auditshow:x:{cid}')])
    if page=='command_cleanup':rows.append([('🟢 פעיל' if d['delete_slash_commands'] else '🔴 כבוי',f'toggle:delete_slash_commands:{cid}')])
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
                     [('🟢 נעילה יומית: פעילה' if d['daily_lock'] else '🔴 נעילה יומית: כבויה',f'toggle:daily_lock:{cid}')],
                     [('🕐 שעת נעילה יומית',f'edit:daily_lock_time:{cid}')],
                     [('🕐 שעת פתיחה יומית',f'edit:daily_unlock_time:{cid}')]])
    if page=='calendar':
        rows.extend([[('🕯️ שבת פעיל/כבוי',f'toggle:shabbat:{cid}'),('✡️ חג פעיל/כבוי',f'toggle:holiday:{cid}')],
                     [('🕐 שעת נעילת שישי',f'edit:friday_time:{cid}')],[('🕐 שעת נעילת ערב חג',f'edit:holiday_time:{cid}')],
                     [('⏱️ דקות אחרי צאת',f'edit:end_offset:{cid}')],
                     [('🌇 דקות אחרי שקיעה לצאת משוער',f'edit:nightfall_minutes:{cid}')]])
        for key,label in [('shabbat_lock_text','הודעת כניסת שבת'),('shabbat_unlock_text','הודעת צאת שבת'),('holiday_lock_text','הודעת כניסת חג'),('holiday_unlock_text','הודעת צאת חג')]:rows.append([(label,f'edit:{key}:{cid}')])
    if page=='replies':rows.extend([[('➕ הוספת תגובה מודרכת',f'wiz:reply:{cid}')],[('📋 רשימת תגובות / עריכה / מחיקה',f'show:replies:{cid}')]])
    if page=='announcements':rows.extend([[('➕ הודעה חוזרת כל X דקות/שעות',f'wiz:announcement:{cid}')],[('📋 רשימה / עריכה / מחיקה',f'show:announcements:{cid}')]])
    if page=='allowlist':rows.append([('📋 רשימת מורשים',f'show:allowlist:{cid}')])
    if page=='backup':
        rows.append([('📤 ייצוא הגדרות',f'export:x:{cid}')])
        rows.append([('👑 שמור כברירת מחדל לכל קבוצה חדשה',f'defaults:x:{cid}')])
    if page in EXPLANATION_LABELS:rows.append([('📖 הסבר שימוש',f'help:{page}:{cid}')])
    rows.append([('⬅️ חזרה להגדרות',f'open:x:{cid}')])
    return kb(*rows)


EDIT_PROMPTS = {
    'daily_lock_time': '🔒 שעת נעילה יומית\nשלח שעה בפורמט HH:MM, למשל 00:42.\nודא שהכפתור ״נעילה יומית״ מופעל.\n/cancel לביטול.',
    'daily_unlock_time': '🔓 שעת פתיחה יומית\nשלח שעה בפורמט HH:MM, למשל 07:00.\n/cancel לביטול.',
    'friday_time': '🕯️ שעת נעילה ביום שישי\nשלח שעה בפורמט HH:MM, למשל 13:00.\n/cancel לביטול.',
    'holiday_time': '🕯️ שעת נעילה בערב חג\nשלח שעה בפורמט HH:MM, למשל 14:00.\n/cancel לביטול.',
    'welcome_buttons': '🔘 שלח כל כפתור בשורה נפרדת: כותרת | https://example.com\n/cancel לביטול.',
    'words': '🚫 שלח מילים אסורות מופרדות בפסיקים.\n/cancel לביטול.',
    'welcome_media': '🖼️ שלח תמונה או סרטון, או ״מחק״ להסרת המדיה.\n/cancel לביטול.',
}
EDIT_NUMBER_LABELS = {'max_warn':'מכסת אזהרות','welcome_seconds':'זמן מחיקת ברכה בשניות','flood_count':'מספר הודעות','flood_seconds':'חלון זמן בשניות','flood_mute':'משך השתקה בשניות','word_mute':'משך השתקה בשניות','end_offset':'דקות המתנה אחרי צאת','nightfall_minutes':'דקות אחרי שקיעה'}
def edit_prompt(key):
    if key in EDIT_PROMPTS:return EDIT_PROMPTS[key]
    if key in EDIT_NUMBER_LABELS:return f'🔢 {EDIT_NUMBER_LABELS[key]}\nשלח מספר שלם.\n/cancel לביטול.'
    return f'✏️ עריכת {key}\nשלח את הטקסט החדש.\n/cancel לביטול.'

async def callbacks(update,context):
    q=update.callback_query;uid=q.from_user.id
    if q.message and q.message.chat.type=='private' and q.data.split(':',1)[0] not in ('verify','warncancel','unmute','approval'):
        panel_remember(uid,q.message.chat_id,q.message.message_id)
    try:
        action,value,cs=q.data.split(':',2)
        cid=0 if action=='ownerexplain' else int(cs)
    except Exception:
        await q.answer('שגיאה');return
    if action in ('ownerexplain','ownertext'):
        if uid!=OWNER or q.message.chat.type!='private':
            await q.answer('רק בעל הבוט',show_alert=True);return
        await q.answer()
        if action=='ownerexplain':
            if value=='systems':
                await panel_from_query(q,'💬 הודעות ותגובות מערכת\n\nבחר הודעה לעריכה:',
                    reply_markup=kb(*([[(label,f'ownertext:view:system,{key}')] for key,label in SYSTEM_LABELS.items()]+[[('⬅️ חזרה לכל הטקסטים','owner:explanations:0')]])))
                return
            key=cs
            if key not in EXPLANATION_LABELS:return
            if value=='select':
                await panel_from_query(q,'📝 '+EXPLANATION_LABELS[key]+'\n\nבחר מה לערוך:',
                    reply_markup=kb([('✏️ הסבר קצר',f'ownertext:view:short,{key}')],
                                    [('📖 הסבר שימוש מפורט',f'ownertext:view:detail,{key}')],
                                    [('⬅️ לכל ההסברים','owner:explanations:0')]))
            return
        try:kind,key=cs.split(',',1)
        except ValueError:return
        if kind not in ('short','detail','system') or key not in (SYSTEM_TEXTS if kind=='system' else EXPLANATION_LABELS):return
        if value=='edit':
            pending_set(uid,0,'owner_text:'+kind+':'+key)
            await panel_from_query(q,'✏️ שלח טקסט חדש עבור '+(SYSTEM_LABELS[key] if kind=='system' else EXPLANATION_LABELS[key])+'.\n/cancel לביטול.',
                reply_markup=kb([('⬅️ חזרה',f'ownertext:view:{kind},{key}')]))
        else:
            if value=='reset':
                meta_set('owner_text:'+kind+':'+key,'')
                if kind=='detail':meta_set('explanation_override:'+key,'')
            text,markup=owner_text_actions(kind,key)
            await panel_from_query(q,('✅ הוחזר לברירת המחדל!\n\n' if value=='reset' else '')+text,reply_markup=markup)
        return
    if action=='owner':
        if uid!=OWNER or q.message.chat.type!='private':await q.answer('רק בעל הבוט',show_alert=True);return
        await q.answer()
        if value=='broadcast':
            candidates=[g2 for g2 in all_groups() if g2['approved'] and g2['active']]
            if not candidates:await panel_from_query(q,'אין קבוצות מאושרות ופעילות.');return
            source=candidates[0]['id'];draft_set(uid,source,'broadcast',{'source':source});pending_set(uid,source,'wizard:broadcast:text')
            await panel_from_query(q,'📣 פרסום מרכזי: שלח טקסט מעוצב, תמונה או סרטון עם כיתוב. לאחר מכן תבחר יעדים ותאשר.');return
        await owner_dashboard(context.bot,q.message.chat_id,value);return
    if action=='ownerbackup':
        if uid!=OWNER or q.message.chat.type!='private':await q.answer('רק בעל הבוט',show_alert=True);return
        await q.answer()
        if value=='create':
            from io import BytesIO
            data=backup_save();buf=BytesIO(json.dumps(data,ensure_ascii=False,indent=2).encode());buf.name='CINEMIX_owner_backup.json'
            await context.bot.send_document(uid,buf,caption='💾 גיבוי מלא של הקבוצות והאזהרות. שמור את הקובץ במקום פרטי.')
        elif value=='restore':
            await panel_from_query(q,'⚠️ שחזור יחליף את הקבוצות והאזהרות במסד הנתונים. יש לבצע רק לאחר בדיקה וגיבוי נוסף.',reply_markup=kb([('⚠️ אשר שחזור אחרון','ownerbackup:confirm:0')],[('❌ ביטול','owner:backups:0')]))
        elif value=='confirm':
            with conn() as c:r=c.execute('SELECT payload FROM owner_backups ORDER BY id DESC LIMIT 1').fetchone()
            if r:
                restore_data=json.loads(r['payload']);backup_save();restore_backup(restore_data)
                await panel_from_query(q,'✅ השחזור בוצע. בדוק את הקבוצות והרשאות הבוט בטלגרם.')
            else:await panel_from_query(q,'אין גיבוי לשחזור.')
        return
    if action=='ownermaintenance':
        if uid!=OWNER or q.message.chat.type!='private':await q.answer('רק בעל הבוט',show_alert=True);return
        await q.answer()
        if value=='text':
            pending_set(uid,0,'maintenance_text');await panel_from_query(q,'✏️ שלח את הודעת התחזוקה שתופיע בקבוצות ובפרטי למנהלים. /cancel לביטול.');return
        if value=='toggle':
            active=meta_get('maintenance','0')=='1';new=not active
            meta_set('maintenance','1' if new else '0')
            txt=meta_get('maintenance_text',system_text('maintenance_notice')) if new else system_text('maintenance_end')
            sent,failed=await owner_notify(context.bot,txt)
            await panel_from_query(q,f'{"🛠️ התחזוקה הופעלה" if new else "✅ התחזוקה הסתיימה"}\nהודעות שנשלחו: {sent}\nשליחות שנכשלו: {failed}',reply_markup=kb([('🟢 הפעל תחזוקה' if not new else '🔴 סיים תחזוקה','ownermaintenance:toggle:0')],[('✏️ ערוך הודעת תחזוקה','ownermaintenance:text:0')],[('⬅️ חזרה','owner:overview:0')]))
        return
    if action=='list':
        await q.answer();await list_groups(context.bot,uid,q.message.chat_id);return
    if action=='guide':
        if uid!=OWNER and not any(g['approved'] and await authorized(context.bot,uid,g['id']) for g in all_groups()):
            await q.answer('אין הרשאה',show_alert=True);return
        await q.answer();await panel_from_query(q,'📖 מדריך CINEMIX\n\n'+'\n\n'.join(explanation_text(k) for k in HELP)[:3900]);return
    if action=='approval':
        if uid!=OWNER:await q.answer('רק בעל הבוט',show_alert=True);return
        if not get_group(cid):await q.answer('קבוצה לא נמצאה');return
        set_group(cid,approved=int(value));await q.answer('עודכן')
        with conn() as c:
            c.execute('DELETE FROM group_requests WHERE chat=?',(cid,))
            c.commit()
        decision=system_text('group_approved') if value=='1' else system_text('group_rejected')
        try:await context.bot.send_message(cid,decision)
        except TelegramError:log.warning('Cannot announce approval in %s',cid)
        with conn() as c:inv=c.execute('SELECT inviter FROM invitations WHERE chat=?',(cid,)).fetchone()
        if inv:
            try:await context.bot.send_message(inv['inviter'],f'{decision}\nקבוצה: {get_group(cid)["title"]}')
            except TelegramError:log.info('Inviter %s has not started private bot chat',inv['inviter'])
        await q.edit_message_text(f'👑 הקבוצה {get_group(cid)["title"]}: {"מאושרת" if value=="1" else "לא מאושרת"}')
        return
    g=get_group(cid)
    if not g or not g.get('active',1):
        # Telegram is authoritative about current membership. Recover a stale
        # active flag or a missing row without requiring /register in the group.
        # A missing database row is never automatically approved.
        try:
            chat = await context.bot.get_chat(cid)
            if await ensure_group(context.bot, chat, notify=True):
                g = get_group(cid)
        except TelegramError as exc:
            log.warning('Cannot recover group %s from callback: %s', cid, exc)
        if not g or not g.get('active',1):
            await q.answer('לא ניתן לאמת כרגע שהבוט נמצא בקבוצה. בדוק הרשאות או נסה שוב.',show_alert=True)
            return
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
    if uid!=OWNER and meta_get('maintenance','0')=='1' and action not in ('open','page','help','stats','health','show'):
        await q.answer('🛠️ הבוט נמצא בתחזוקה. שינוי הגדרות אינו זמין כרגע.',show_alert=True);return
    if action=='wiz':
        if q.message.chat.type!='private':await q.answer('רק בפרטי',show_alert=True);return
        await q.answer()
        if value=='reply':
            draft_set(uid,cid,'reply',{})
            pending_set(uid,cid,'wizard:reply:trigger')
            await panel_from_query(q,'🤖 יצירת תגובה אוטומטית\nשלב 1/5: איזו מילה או ביטוי יפעילו את התגובה?')
        elif value=='announcement':
            draft_set(uid,cid,'announcement',{})
            pending_set(uid,cid,'wizard:announcement:minutes')
            await panel_from_query(q,'⏰ פרסום אוטומטי\nשלב 1/4: כל כמה דקות לפרסם? לדוגמה 180 לפרסום כל 3 שעות.')
        elif value=='broadcast':
            if uid==OWNER and (not g or not g['approved']):
                candidates=[x for x in all_groups() if x['approved'] and x['active']]
                if not candidates:
                    await panel_from_query(q,'❌ אין קבוצות מאושרות ופעילות לפרסום.');return
                cid=candidates[0]['id']
            draft_set(uid,cid,'broadcast',{'source':cid})
            pending_set(uid,cid,'wizard:broadcast:text')
            await panel_from_query(q,'📣 פרסום חד־פעמי\nשלח טקסט, תמונה עם כיתוב או סרטון עם כיתוב. בהמשך תבחר יעד ותאשר.')
        return
    if action=='wizardmode':
        d=draft_get(uid)
        if not d or d[0]!=cid or d[1]!='reply':await q.answer('ההגדרה פגה');return
        payload=d[2];payload['mode']=value;draft_set(uid,cid,'reply',payload)
        pending_set(uid,cid,'wizard:reply:text')
        await q.answer();await panel_from_query(q,'שלב 3/5: מה הבוט יענה? שלח טקסט.')
        return
    if action=='wizardbool':
        d=draft_get(uid)
        if not d or d[0]!=cid:await q.answer('ההגדרה פגה');return
        payload=d[2]
        if d[1]=='reply':
            if value=='buttons':
                if payload.get('buttons_choice') is None:
                    payload['buttons_choice']=True;draft_set(uid,cid,'reply',payload);pending_set(uid,cid,'wizard:reply:buttons')
                    await q.answer();await panel_from_query(q,'שלב 4/5: שלח כפתורים, כל שורה: כותרת | https://example.com. שלח /skip לדלג.')
                    return
            if value=='nobuttons':payload['buttons']=[]
            draft_set(uid,cid,'reply',payload)
            pending_set(uid,cid,'wizard:reply:media')
            await q.answer();await panel_from_query(q,'שלב 5/5: שלח תמונה או סרטון לתגובה, או /skip לדלג.')
            return
        if d[1]=='announcement':
            payload['delete_previous']=(value=='deleteyes')
            draft_set(uid,cid,'announcement',payload)
            pending_set(uid,cid,'wizard:announcement:buttons')
            await q.answer();await panel_from_query(q,'שלב 4/4: כפתורים בפורמט כותרת | קישור, או /skip לדלג. לאחר מכן תראה תצוגה מקדימה.')
            return
    if action=='wizardpreview' and value=='cancel':
        draft_clear(uid);clear_pending(uid);await q.answer('בוטל');await panel_from_query(q,'❌ הפרסום בוטל');return
    if action=='wizardpreview':
        d=draft_get(uid)
        if not d or d[0]!=cid:await q.answer('אין טיוטה. התחל פרסום חדש.',show_alert=True);return
        await q.answer()
        payload=d[2]
        if value=='save' and d[1] in ('reply','announcement'):
            data=cfg(cid);kind='replies' if d[1]=='reply' else 'announcements'
            payload.pop('buttons_choice',None)
            if kind=='announcements':payload['last']=int(time.time());payload['last_mid']=None
            data[kind].append(payload);save_cfg(cid,data);draft_clear(uid);clear_pending(uid)
            await refresh_settings(q,cid,'replies' if kind=='replies' else 'announcements','✅ נשמר בהצלחה!');return
        if value=='send' and d[1]=='broadcast':
            targets=payload.get('targets',[])
            sent=0;failed=[]
            for target in targets:
                g2=get_group(target)
                if not g2 or not g2['approved'] or not g2['active']:continue
                if uid!=OWNER and not await authorized(context.bot,uid,target):continue
                try:
                    await send_formatted(context.bot,target,payload['text'],markup=buttons(payload.get('buttons')),media=payload.get('media'))
                    sent+=1;metric(target,'broadcasts')
                except TelegramError as e:failed.append(f'{g2["title"]}: {str(e)[:70]}')
                await asyncio.sleep(0.12)
            draft_clear(uid);clear_pending(uid)
            await panel_from_query(q,f'📣 הפרסום הסתיים. הצלחות: {sent}; כישלונות: {len(failed)}'+('\n'+'\n'.join(failed[:12]) if failed else ''))
            return
    if action=='broadcastpick':
        if uid!=OWNER:await q.answer('רק בעל הבוט');return
        d=draft_get(uid)
        if not d or d[1]!='broadcast':await q.answer('אין טיוטה. התחל פרסום חדש.',show_alert=True);return
        payload=d[2];targets=payload.get('targets',[])
        if value=='done':
            if not targets:await q.answer('בחר לפחות קבוצה אחת',show_alert=True);return
            await q.answer();await panel_from_query(q,f'📣 תצוגה מקדימה\n\n{html.unescape(re.sub(r'<[^>]*>', '', payload.get('text','').removeprefix('HTML:')))[:1200]}\n\nיעדים: {len(targets)}\nלא נשלח עדיין.',reply_markup=kb([('✅ אשר ושלח',f'wizardpreview:send:{d[0]}'),('❌ בטל',f'wizardpreview:cancel:{d[0]}')]))
            return
        try:chosen=int(value)
        except ValueError:await q.answer('שגיאה');return
        g2=get_group(chosen)
        if not g2 or not g2['approved'] or not g2['active']:await q.answer('הקבוצה אינה מאושרת');return
        if chosen in targets:targets.remove(chosen)
        else:targets.append(chosen)
        payload['targets']=targets;cid=d[0];draft_set(uid,cid,'broadcast',payload)
        await q.answer('עודכן')
        await q.edit_message_reply_markup(broadcast_picker(payload))
        return
    if action=='broadcasttarget' and value=='choose':
        if uid!=OWNER:await q.answer('רק בעל הבוט');return
        d=draft_get(uid)
        if not d or d[1]!='broadcast':await q.answer('אין טיוטה',show_alert=True);return
        await q.answer();await panel_from_query(q,'📍 בחר קבוצות לפרסום ואז לחץ סיום:',reply_markup=broadcast_picker(d[2]))
        return
    if action=='broadcasttarget':
        d=draft_get(uid)
        if not d or d[1]!='broadcast':await q.answer('אין טיוטה. התחל פרסום חדש.',show_alert=True);return
        payload=d[2]
        if value=='all' and uid==OWNER:targets=[g2['id'] for g2 in all_groups() if g2['approved'] and g2['active']]
        elif value=='one':targets=[d[0]]
        else:await q.answer('אין הרשאה');return
        payload['targets']=targets;cid=d[0];draft_set(uid,cid,'broadcast',payload)
        await q.answer();await panel_from_query(q,f'📣 תצוגה מקדימה\n\n{html.unescape(re.sub(r'<[^>]*>', '', payload.get('text','').removeprefix('HTML:')))[:1200]}\n\nיעדים: {len(targets)}\nלא נשלח עדיין.',reply_markup=kb([('✅ אשר ושלח',f'wizardpreview:send:{d[0]}'),('❌ בטל',f'wizardpreview:cancel:{cid}')]))
        return
    if action=='ownerall':
        if uid!=OWNER:await q.answer('רק בעל הבוט');return
        await q.answer()
        groups=[g2 for g2 in all_groups() if g2['approved']]
        await owner_dashboard(context.bot,q.message.chat_id,'overview')
        return
    if action=='health':
        await q.answer()
        try:
            me=await context.bot.get_me();member=await context.bot.get_chat_member(cid,me.id)
            checks=[('מנהל',member.status=='administrator'),('מחיקת הודעות',bool(getattr(member,'can_delete_messages',False))),('חסימה/השתקה',bool(getattr(member,'can_restrict_members',False))),('נעיצת הודעות',bool(getattr(member,'can_pin_messages',False)))]
            await panel_from_query(q,'🩺 בדיקת הרשאות\n'+'\n'.join(('✅ ' if ok else '❌ ')+name for name,ok in checks))
        except TelegramError as e:await panel_from_query(q,f'❌ בדיקה נכשלה: {e}')
        return
    if action=='simstart':
        pending_set(uid,cid,'simulate');await q.answer();await panel_from_query(q,'🧪 שלח טקסט לדוגמה. לא תימחק הודעה ולא תינתן אזהרה.');return
    if action=='auditshow':
        with conn() as c:rows=c.execute('SELECT * FROM audit WHERE chat=? ORDER BY id DESC LIMIT 20',(cid,)).fetchall()
        msg='📋 יומן פעולות\n'+('\n'.join(f'{datetime.fromtimestamp(r["created"],TZ):%d/%m %H:%M} | {r["actor"]} | {r["action"]} | {r["detail"][:55]}' for r in rows) if rows else 'אין פעולות מתועדות עדיין.')
        await q.answer();await panel_from_query(q,msg[:3900],reply_markup=kb([('⬅️ חזרה ליומן',f'page:audit:{cid}') ]));return
    if action=='rulespublish':
        await q.answer();rules=cfg(cid).get('rules_text','')
        if not rules:await panel_from_query(q,'קודם הגדר חוקי קבוצה.');return
        await send_formatted(context.bot,cid,rules);audit(cid,uid,'publish_rules');await refresh_settings(q,cid,'rules','✅ החוקים פורסמו.');return
    if action=='stats':
        await q.answer()
        with conn() as c:rows=c.execute('SELECT kind,amount FROM stats WHERE chat=?',(cid,)).fetchall()
        await panel_from_query(q,'📊 סטטיסטיקות קבוצה\n'+('\n'.join(f'{r["kind"]}: {r["amount"]}' for r in rows) if rows else 'אין נתונים עדיין.'))
        return
    if action in ('annswitch','annshabbat','annhours'):
        try:index=int(value);item=cfg(cid)['announcements'][index]
        except (ValueError,IndexError):await q.answer('לא נמצא');return
        if action=='annhours':
            pending_set(uid,cid,f'annhours:{index}')
            await q.answer();await panel_from_query(q,'🕐 שלח טווח שעות לדוגמה 09:00-23:00, או מחק כדי לפרסם בכל שעה.');return
        field='enabled' if action=='annswitch' else 'skip_shabbat_holiday'
        item[field]=not item.get(field,field=='enabled')
        d=cfg(cid);d['announcements'][index]=item;save_cfg(cid,d)
        await q.answer('עודכן');await panel_from_query(q,f'✅ עודכן: {item[field]}',reply_markup=page_keyboard(cid,'announcements'));return
    if action=='annprev':
        try:index=int(value);item=cfg(cid)['announcements'][index]
        except (ValueError,IndexError):await q.answer('לא נמצא');return
        item['delete_previous']=not item.get('delete_previous',False)
        d=cfg(cid);d['announcements'][index]=item;save_cfg(cid,d)
        await q.answer('עודכן');await panel_from_query(q,'🗑️ מחיקת פרסום קודם: '+('כן' if item['delete_previous'] else 'לא'))
        return
    if action=='open':
        await q.answer();await panel_from_query(q,f'⚙️ {g["title"]}\nבחר הגדרה:',reply_markup=menu(cid));return
    if action=='page':
        await q.answer()
        await panel_from_query(q,settings_page_text(value) if value!='guide' else '\n\n'.join(explanation_text(k) for k in HELP)[:3900],
                                   reply_markup=page_keyboard(cid,value) if value!='guide' else kb([('⬅️ חזרה להגדרות',f'open:x:{cid}')]))
        return
    if action=='help':
        await q.answer();await panel_from_query(q,explanation_text(value),reply_markup=kb([('⬅️ חזרה',f'page:{value}:{cid}')]))
        return
    if action=='toggle':
        if value not in ('links','welcome','flood','verify','service_delete','channel_posts_delete','shabbat','holiday','daily_lock','stealth','delete_slash_commands'):await q.answer('לא נתמך');return
        new_state=not cfg(cid)[value]
        set_cfg(cid,value,new_state);await q.answer('נשמר')
        await refresh_settings(q,cid,FIELD_PAGES[value],'✅ ההגדרה עודכנה.')
        return
    if action=='cycle' and value=='forward_filter':
        modes=['allow','channels','all'];current=cfg(cid)['forward_filter'];set_cfg(cid,'forward_filter',modes[(modes.index(current)+1)%3]);await q.answer('נשמר');await refresh_settings(q,cid,'forward','✅ הסינון עודכן.');return
    if action=='cycle' and value=='word_action':
        opts=['delete','warn','mute','ban'];cur=cfg(cid)['word_action'];set_cfg(cid,'word_action',opts[(opts.index(cur)+1)%len(opts)]);await q.answer('נשמר');await refresh_settings(q,cid,'words','✅ העונש עודכן.');return
    if action=='edit':
        if q.message.chat.type!='private':
            await q.answer('עריכת הגדרות בפרטי בלבד',show_alert=True);return
        PENDING[uid]=(cid,value)
        with conn() as c:
            c.execute('INSERT OR REPLACE INTO pending_edits(uid,chat,field) VALUES (?,?,?)',(uid,cid,value));c.commit()
        await q.answer()
        await panel_from_query(q,edit_prompt(value))
        return
    if action=='show':
        await q.answer();data=cfg(cid).get(value,[])
        if not data:
            await panel_from_query(q,'הרשימה ריקה.',reply_markup=kb([('⬅️ חזרה',f'page:{value if value in ("replies","announcements") else "allowlist"}:{cid}')]))
            return
        rows=[]
        for i,item in enumerate(data[:35]):
            rows.append([('🗑️ מחק '+str(i+1),f'remove:{value},{i}:{cid}')])
            if value in ('replies','announcements'):
                rows.append([('✏️ טקסט '+str(i+1),f'itemedit:{value},{i}:{cid}'),('🔘 כפתורים',f'itembuttons:{value},{i}:{cid}'),('🖼️ מדיה',f'itemmedia:{value},{i}:{cid}')])
                if value=='announcements':
                    rows.append([('🗑️ קודם: '+('כן' if item.get('delete_previous') else 'לא'),f'annprev:{i}:{cid}'),('⏸️ הפעלה',f'annswitch:{i}:{cid}')])
                    rows.append([('🕯️ שבת וחג',f'annshabbat:{i}:{cid}'),('🕐 שעות',f'annhours:{i}:{cid}')])
        rows.append([('⬅️ חזרה',f'page:{value if value in ("replies","announcements") else "allowlist"}:{cid}')])
        lines=[f'{i+1}. {str(item)[:100]}' for i,item in enumerate(data[:20])]
        await panel_from_query(q,'📋 רשימה\n'+'\n'.join(lines)[:3500],reply_markup=kb(*rows))
        return
    if action in ('itembuttons','itemmedia'):
        try:key,index=value.split(',');index=int(index);assert key in ('replies','announcements');cfg(cid)[key][index]
        except Exception:await q.answer('לא נמצא');return
        PENDING[uid]=(cid,f'{action}:{key}:{index}')
        with conn() as c:
            c.execute('INSERT OR REPLACE INTO pending_edits(uid,chat,field) VALUES (?,?,?)',(uid,cid,f'{action}:{key}:{index}'));c.commit()
        await q.answer()
        await panel_from_query(q,'🔘 שלח כפתורים בשורות: כותרת | https://example.com\nאו שלח תמונה/וידאו. כתוב מחק להסרת מדיה/כפתורים.');return
    if action=='itemedit':
        try:key,index=value.split(',');index=int(index);item=cfg(cid)[key][index]
        except Exception:await q.answer('לא נמצא');return
        PENDING[uid]=(cid,f'item:{key}:{index}')
        with conn() as c:
            c.execute('INSERT OR REPLACE INTO pending_edits(uid,chat,field) VALUES (?,?,?)',(uid,cid,f'item:{key}:{index}'));c.commit()
        await q.answer();await panel_from_query(q,'✏️ שלח הגדרה חדשה:\nלתגובה: טריגר | exact/contains | טקסט\nלהודעה חוזרת: דקות | טקסט\nהעיצוב של טלגרם נשמר בהודעות טקסט.');return
    if action=='remove':
        try:key,index=value.split(',');index=int(index);data=cfg(cid)[key];data.pop(index);set_cfg(cid,key,data)
        except Exception:await q.answer('לא נמצא');return
        await q.answer('נמחק');await q.edit_message_text('🗑️ הפריט נמחק',reply_markup=page_keyboard(cid,'replies' if key=='replies' else 'announcements' if key=='announcements' else 'allowlist'));return
    if action=='defaults':
        if uid!=OWNER:await q.answer('רק בעל הבוט',show_alert=True);return
        with conn() as c:c.execute("INSERT OR REPLACE INTO meta(key,val) VALUES ('owner_defaults',?)",(json.dumps(cfg(cid),ensure_ascii=False),));c.commit()
        await q.answer('נשמר');await panel_from_query(q,'👑 הגדרות הקבוצה נשמרו כברירת מחדל לקבוצות חדשות.');return
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
        await q.answer();await change_lock(context.bot,cid,action=='lock','manual');await refresh_settings(q,cid,'lock','✅ פעולת הנעילה בוצעה.');return
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
            await panel_from_input(update,context,'ℹ️ אין כרגע הגדרה שממתינה לערך. בחר הגדרה בתפריט, או שלח /setstart כדי לשנות את הודעת הפתיחה.')
        return
    cid,key=pending
    if meta_get('maintenance','0')=='1' and uid!=OWNER and key not in ('simulate',):
        await panel_from_input(update,context,'🛠️ הבוט בתחזוקה. לא ניתן לשנות הגדרות כעת.');return
    if key.startswith('wizard:'):
        await wizard_input(update,context,cid,key)
        return
    if key=='simulate':
        text=(update.message.text or update.message.caption or '')
        d=cfg(cid);reasons=[]
        if d['links'] and re.search(r'(?i)(https?://|www\.|t\.me/)',text):reasons.append('🔗 קישור אסור — מחיקה ואזהרה')
        if d['words'] and any(w in text.lower() for w in d['words']):reasons.append('🚫 מילה אסורה — '+d['word_action'])
        await panel_from_input(update,context,'🧪 סימולציה בלבד\n'+('\n'.join(reasons) if reasons else '✅ לא זוהתה הפרה לפי בדיקת הטקסט. בדיקת הצפה דורשת רצף הודעות ולכן אינה נבדקת כאן.'))
        clear_pending(uid);return
    if key.startswith('annhours:'):
        group=get_group(cid)
        if not group or not group['approved'] or (uid!=OWNER and not await authorized(context.bot,uid,cid)):
            clear_pending(uid);return
        try:
            index=int(key.split(':')[1]);raw=(update.message.text or '').strip()
            if raw=='מחק':hours=None
            else:
                m=re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d',raw)
                if not m:raise ValueError()
                hours=[x.strip() for x in raw.split('-')]
            d=cfg(cid);d['announcements'][index]['active_hours']=hours;save_cfg(cid,d);clear_pending(uid)
            await private_settings_result(update.message,cid,'announcements','✅ שעות הפעילות נשמרו')
        except (ValueError,IndexError,KeyError):await panel_from_input(update,context,'❌ שלח 09:00-23:00 או מחק')
        return
    if key.startswith('owner_text:'):
        if uid!=OWNER:return
        _,kind,text_key=key.split(':',2)
        if kind not in ('short','detail','system') or text_key not in (SYSTEM_TEXTS if kind=='system' else EXPLANATION_LABELS):
            clear_pending(uid);return
        value=(update.message.text or update.message.caption or '').strip()
        if not value or len(value)>3500:
            await panel_from_input(update,context,'❌ שלח טקסט באורך 1–3500 תווים.');return
        meta_set('owner_text:'+kind+':'+text_key,value)
        clear_pending(uid)
        text,markup=owner_text_actions(kind,text_key)
        await panel_from_input(update,context,'✅ הטקסט נשמר!\n\n'+text,reply_markup=markup)
        return
    if key.startswith('owner_explanation:'):
        if uid!=OWNER:return
        explain_key=key.split(':',1)[1]
        if explain_key not in EXPLANATION_LABELS:
            clear_pending(uid);return
        value=(update.message.text or update.message.caption or '').strip()
        if not value or len(value)>3500:
            await panel_from_input(update,context,'❌ שלח הסבר באורך 1–3500 תווים.');return
        meta_set('explanation_override:'+explain_key,value)
        clear_pending(uid)
        await panel_from_input(update,context,'✅ ההסבר נשמר!\n\n'+value,
            reply_markup=kb([('✏️ עריכה נוספת',f'ownerexplain:edit:{explain_key}')],
                            [('⬅️ לכל ההסברים','owner:explanations:0')]))
        return
    if key=='maintenance_text':
        if uid!=OWNER:return
        value=(update.message.text or '').strip()
        if not value or len(value)>3500:await panel_from_input(update,context,'שלח טקסט עד 3500 תווים.');return
        meta_set('maintenance_text',value);clear_pending(uid)
        await panel_from_input(update,context,'✅ הודעת התחזוקה נשמרה.');return
    if key=='stealth_reply':
        group=get_group(cid)
        draft=draft_get(uid)
        if not group or not group['approved'] or not draft or draft[1]!='stealth_reply' or not await authorized(context.bot,uid,cid):
            clear_pending(uid);draft_clear(uid);await panel_from_input(update,context,'הבקשה אינה זמינה.');return
        payload=draft[2]
        try:
            media=None
            if update.message.photo:media={'type':'photo','id':update.message.photo[-1].file_id}
            if update.message.video:media={'type':'video','id':update.message.video.file_id}
            body=message_formatted(update.message) or ('📷' if media else '')
            if not body and not media:await panel_from_input(update,context,'שלח טקסט, תמונה או סרטון.');return
            await send_formatted(context.bot,cid,body,markup=None,media=media,reply_to=payload['mid'])
            audit(cid,uid,'stealth_reply',str(payload['mid']))
            clear_pending(uid);draft_clear(uid)
            await panel_from_input(update,context,'✅ התשובה פורסמה בקבוצה בשם הבוט.')
        except TelegramError as exc:await panel_from_input(update,context,'❌ לא ניתן לפרסם את התשובה: '+str(exc)[:120])
        return
    if key=='owner_start_text':
        if uid!=OWNER:return
        value=(update.message.text or update.message.caption or '').strip()
        if not value or len(value)>3500:
            await panel_from_input(update,context,'❌ שלח טקסט באורך 1–3500 תווים. ההגדרה עדיין ממתינה.')
            return
        with conn() as c:
            c.execute("INSERT OR REPLACE INTO meta(key,val) VALUES ('regular_start_text',?)",(value,))
            c.execute('DELETE FROM pending_edits WHERE uid=?',(uid,));c.commit()
        PENDING.pop(uid,None)
        await panel_from_input(update,context,'✅ הודעת הפתיחה למשתמשים נשמרה!')
        return
    group=get_group(cid)
    if not group or not group.get('active',1) or (uid!=OWNER and (not group['approved'] or not await authorized(context.bot,uid,cid))):
        await panel_from_input(update,context,'❌ אין גישה לקבוצה הזאת כרגע.')
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
            save_cfg(cid,d);clear_pending(uid);await private_settings_result(update.message,cid,'replies' if kind=='replies' else 'announcements');return
        elif key.startswith('item:'):
            _,kind,index=key.split(':');index=int(index)
            if kind=='replies':
                trigger,mode,response=[x.strip() for x in raw.split('|',2)]
                assert trigger and mode in ('exact','contains') and response
                d[kind][index].update(trigger=trigger,mode=mode,text=response)
            elif kind=='announcements':
                minutes,response=raw.split('|',1);minutes=int(minutes);assert minutes>0
                d[kind][index].update(minutes=minutes,text=response.strip(),last=int(time.time()))
            save_cfg(cid,d);clear_pending(uid);await private_settings_result(update.message,cid,'replies' if kind=='replies' else 'announcements','✅ נערך בהצלחה');return
        elif key=='add_reply':
            trigger,mode,response=[x.strip() for x in raw.split('|',2)]
            assert mode in ('exact','contains') and trigger and response
            d['replies'].append({'trigger':trigger,'mode':mode,'text':response,'buttons':[]});save_cfg(cid,d)
            clear_pending(uid);await private_settings_result(update.message,cid,'replies','✅ התגובה נוספה');return
        elif key=='add_announcement':
            minutes,response=raw.split('|',1);minutes=int(minutes.strip());assert minutes>=1
            d['announcements'].append({'minutes':minutes,'text':response.strip(),'last':int(time.time())});save_cfg(cid,d)
            clear_pending(uid);await private_settings_result(update.message,cid,'announcements','✅ ההודעה החוזרת נוספה');return
        else:val='HTML:'+update.message.text_html if update.message.text and update.message.entities else raw
        set_cfg(cid,key,val)
        clear_pending(uid)
        await private_settings_result(update.message,cid,FIELD_PAGES.get(key,'lock'))
    except Exception:
        log.exception('Private input validation failed for field %s',key)
        await panel_from_input(update,context,'❌ פורמט לא תקין. ההגדרה עדיין ממתינה — שלח ערך תקין או /cancel.')


def parse_url_buttons(raw):
    result=[]
    for line in raw.splitlines():
        if not line.strip():continue
        title,url=[x.strip() for x in line.split('|',1)]
        if not title or not url.startswith(('https://','http://','tg://')):raise ValueError('קישור לא תקין')
        result.append({'text':title,'url':url})
    return result


async def wizard_preview(update,context,cid,kind,payload):
    if kind=='reply':
        desc=f'🤖 תצוגה מקדימה\nטריגר: {payload["trigger"]}\nהתאמה: {payload["mode"]}\nתגובה: {payload["text"]}\nכפתורים: {len(payload.get("buttons",[]))}\nמדיה: {"כן" if payload.get("media") else "לא"}'
    else:
        desc=f'⏰ תצוגה מקדימה\nכל {payload["minutes"]} דקות\n{payload["text"]}\nמחיקת הקודם: {"כן" if payload.get("delete_previous") else "לא"}\nכפתורים: {len(payload.get("buttons",[]))}'
    await panel_from_input(update,context,desc,reply_markup=kb([('✅ שמור',f'wizardpreview:save:{cid}'),('❌ בטל',f'wizardpreview:cancel:{cid}')]))


async def wizard_input(update,context,cid,key):
    uid=update.effective_user.id
    d=draft_get(uid)
    if not d or d[0]!=cid:clear_pending(uid);await panel_from_input(update,context,'❌ הטיוטה לא נמצאה, התחל מחדש.');return
    _,kind,payload=d
    if uid!=OWNER:
        g=get_group(cid)
        if not g or not g['approved'] or not await authorized(context.bot,uid,cid):clear_pending(uid);draft_clear(uid);return
    step=key.split(':')[-1]
    raw=(update.message.text or update.message.caption or '').strip()
    try:
        if kind=='reply':
            if step=='trigger':
                if not raw or len(raw)>120:raise ValueError()
                payload['trigger']=raw;draft_set(uid,cid,kind,payload);clear_pending(uid)
                await panel_from_input(update,context,'שלב 2/5: מתי להגיב?',reply_markup=kb([('🎯 בדיוק הביטוי',f'wizardmode:exact:{cid}'),('🔎 גם בתוך משפט',f'wizardmode:contains:{cid}')]))
                return
            if step=='text':
                if not raw:raise ValueError()
                payload['text']=message_formatted(update.message);draft_set(uid,cid,kind,payload);clear_pending(uid)
                await panel_from_input(update,context,'שלב 4/5: להוסיף כפתורים?',reply_markup=kb([('🔘 כן',f'wizardbool:buttons:{cid}'),('ללא כפתורים',f'wizardbool:nobuttons:{cid}')]))
                return
            if step=='buttons':
                payload['buttons']=parse_url_buttons(raw)
                payload.pop('buttons_choice',None)
                draft_set(uid,cid,kind,payload);pending_set(uid,cid,'wizard:reply:media')
                await panel_from_input(update,context,'שלב 5/5: שלח תמונה או סרטון, או /skip לדלג.');return
            if step=='media':
                if update.message.photo:payload['media']={'type':'photo','id':update.message.photo[-1].file_id}
                elif update.message.video:payload['media']={'type':'video','id':update.message.video.file_id}
                else:raise ValueError('שלח תמונה או סרטון, או /skip')
                draft_set(uid,cid,kind,payload);clear_pending(uid)
                await wizard_preview(update,context,cid,kind,payload);return
        if kind=='announcement':
            if step=='minutes':
                minutes=int(raw)
                if not 1<=minutes<=525600:raise ValueError()
                payload['minutes']=minutes;draft_set(uid,cid,kind,payload);pending_set(uid,cid,'wizard:announcement:text')
                await panel_from_input(update,context,'שלב 2/4: שלח טקסט לפרסום, או תמונה/וידאו עם כיתוב.');return
            if step=='text':
                if not raw and not (update.message.photo or update.message.video):raise ValueError()
                payload['text']=message_formatted(update.message) or ' '
                if update.message.photo:payload['media']={'type':'photo','id':update.message.photo[-1].file_id}
                if update.message.video:payload['media']={'type':'video','id':update.message.video.file_id}
                draft_set(uid,cid,kind,payload);clear_pending(uid)
                await panel_from_input(update,context,'שלב 3/4: למחוק את הפרסום הקודם לפני הפרסום הבא?',reply_markup=kb([('🗑️ כן',f'wizardbool:deleteyes:{cid}'),('לא',f'wizardbool:deleteno:{cid}')]))
                return
            if step=='buttons':
                payload['buttons']=parse_url_buttons(raw);draft_set(uid,cid,kind,payload);clear_pending(uid)
                await wizard_preview(update,context,cid,kind,payload);return
        if kind=='broadcast' and step=='text':
            if not raw and not (update.message.photo or update.message.video):raise ValueError()
            payload['text']=message_formatted(update.message) or ' '
            if update.message.photo:payload['media']={'type':'photo','id':update.message.photo[-1].file_id}
            if update.message.video:payload['media']={'type':'video','id':update.message.video.file_id}
            draft_set(uid,cid,kind,payload);clear_pending(uid)
            rows=[[('📍 לקבוצה הזאת',f'broadcasttarget:one:{cid}')]]
            if uid==OWNER:
                rows.append([('📍 בחירת מספר קבוצות',f'broadcasttarget:choose:{cid}')])
                rows.append([('🌐 לכל הקבוצות המאושרות',f'broadcasttarget:all:{cid}')])
            await panel_from_input(update,context,'📣 בחר יעד לפרסום. לא נשלח עדיין.',reply_markup=kb(*rows));return
    except (ValueError,TypeError,KeyError,IndexError) as e:
        await panel_from_input(update,context,'❌ הערך לא תקין. נסה שוב או /cancel. '+str(e)[:100]);return


async def skip(update,context):
    uid=update.effective_user.id
    with conn() as c:r=c.execute('SELECT chat,field FROM pending_edits WHERE uid=?',(uid,)).fetchone()
    if not r or not r['field'].startswith('wizard:'):return
    cid=r['chat'];step=r['field'].split(':')[-1];d=draft_get(uid)
    if not d or d[0]!=cid:return
    _,kind,payload=d
    if kind=='reply' and step=='buttons':
        payload['buttons']=[];draft_set(uid,cid,kind,payload);pending_set(uid,cid,'wizard:reply:media')
        await panel_from_input(update,context,'שלח תמונה או סרטון, או /skip לדלג.');return
    if kind=='reply' and step=='media':
        draft_set(uid,cid,kind,payload);clear_pending(uid);await wizard_preview(update,context,cid,kind,payload);return
    if kind=='announcement' and step=='buttons':
        payload['buttons']=[];draft_set(uid,cid,kind,payload);clear_pending(uid);await wizard_preview(update,context,cid,kind,payload)


async def cancel(update,context):
    PENDING.pop(update.effective_user.id,None)
    draft_clear(update.effective_user.id)
    clear_pending(update.effective_user.id)
    await panel_update(context.bot,update.effective_user.id,'❌ בוטל. חזור לתפריט הניהול באמצעות /manage.')
    # Keep /cancel in the private history as well.


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
        metric(cid,'joins')
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
    d=cfg(cid);n=warn_count(cid,user.id,1);metric(cid,'warnings')
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
    if msg.forward_origin and d.get('forward_filter') in ('channels','all'):
        from telegram import MessageOriginChannel
        if d['forward_filter']=='all' or isinstance(msg.forward_origin,MessageOriginChannel):
            if not await authorized(context.bot,u.id,cid):
                await safe_delete(context.bot,cid,msg.message_id);audit(cid,u.id,'forward_deleted');return
    with conn() as c:
        c.execute('INSERT OR IGNORE INTO seen VALUES (?,?,?)',(cid,msg.message_id,int(time.time())));c.commit()
    exempt=await authorized(context.bot,u.id,cid) or u.id in d['allowlist']
    text=(msg.text or msg.caption or '')
    if exempt:
        await run_replies(context.bot,cid,d,text,u,msg.message_id)
        return
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
    await run_replies(context.bot,cid,d,text,u,msg.message_id)


async def run_replies(bot,cid,settings,text,user,reply_to):
    body=text.casefold().strip()
    for item in settings.get('replies',[]):
        trigger=item.get('trigger','').casefold()
        if not trigger:continue
        if (item.get('mode')=='exact' and body==trigger) or (item.get('mode')=='contains' and trigger in body):
            try:
                await send_formatted(bot,cid,item.get('text',''),user,buttons(item.get('buttons')),item.get('media'),reply_to)
                metric(cid,'auto_replies')
            except TelegramError:log.exception('Auto reply failed in group %s',cid)
            break


async def commands(update,context):
    msg=update.message;cid=msg.chat_id;u=msg.from_user;cmd=msg.text.split()[0].split('@')[0].lower().lstrip('/')
    if not await authorized(context.bot,u.id,cid):return
    g=get_group(cid)
    if not g or not g['approved']:return
    await safe_delete(context.bot,cid,msg.message_id)
    if meta_get('maintenance','0')=='1' and u.id!=OWNER:
        try:await context.bot.send_message(u.id,'🛠️ הבוט נמצא בתחזוקה, פעולות ניהול זמנית אינן זמינות.')
        except TelegramError:pass
        return
    target=msg.reply_to_message.from_user if msg.reply_to_message else None
    args=msg.text.split()[1:]
    if cmd=='reply':
        if not cfg(cid).get('stealth'):
            try:await context.bot.send_message(u.id,system_text('stealth_disabled'))
            except TelegramError:pass
            return
        if not msg.reply_to_message:return
        draft_set(u.id,cid,'stealth_reply',{'mid':msg.reply_to_message.message_id})
        pending_set(u.id,cid,'stealth_reply')
        try:await context.bot.send_message(u.id,system_text('stealth_prompt'))
        except TelegramError:pass
        return
    audit(cid,u.id,'command',cmd)
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
            await context.bot.send_message(cid,system_text('import_prompt'));return
        try:
            f=await context.bot.get_file(doc.file_id);raw=await f.download_as_bytearray()
            data=json.loads(raw.decode('utf-8'))
            if data.get('format')!='cinemix-settings-v1' or not isinstance(data.get('settings'),dict):raise ValueError()
            clean={**copy.deepcopy(DEFAULT),**{k:v for k,v in data['settings'].items() if k in DEFAULT}}
            PENDING[('import',u.id,cid)]=clean
            await context.bot.send_message(cid,'⚠️ ייבוא זה יחליף את כל הגדרות הקבוצה. לא יועברו אישורי קבוצות.',reply_markup=kb([('✅ אישור ייבוא',f'import:x:{cid}')]))
        except Exception:await context.bot.send_message(cid,system_text('import_invalid'))
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
            if not original:
                log.error('Refusing to unlock %s without saved permissions',cid)
                return
            await bot.set_chat_permissions(cid,ChatPermissions(**original))
            set_group(cid,locked=0,permissions=None,lock_reason=None)
            key='holiday_unlock_text' if g['lock_reason']=='holiday' else 'shabbat_unlock_text' if g['lock_reason']=='shabbat' else 'unlock_text'
        await send_formatted(bot,cid,d[key])
        audit(cid,OWNER,'lock' if lock else 'unlock',reason)
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
    if settings.get('daily_lock'):
        start,end=settings['daily_lock_time'],settings['daily_unlock_time']
        hm=now.strftime('%H:%M')
        if start!=end and ((start<=hm<end) if start<end else (hm>=start or hm<end)):
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
    if meta_get('backup_day')!=now.strftime('%Y-%m-%d'):
        backup_save();meta_set('backup_day',now.strftime('%Y-%m-%d'))
    for g in all_groups():
        cid=g['id']
        if not g['approved'] or not g['active']:continue
        d=cfg(cid)
        await calendar_tick(context.bot,cid,g,d,now)
        # Daily schedules, fixed Jerusalem local time. Prevent repeated execution in same minute.
        hm=now.strftime('%H:%M')
        if d['daily_lock'] and d['daily_lock_time'] != d['daily_unlock_time']:
            # Desired state based on Israel local clock; survives missed ticks and restarts.
            start,end=d['daily_lock_time'],d['daily_unlock_time']
            should_lock = (start <= hm < end) if start < end else (hm >= start or hm < end)
            current=get_group(cid)
            if should_lock and not current['locked']:
                await change_lock(context.bot,cid,True,'daily')
            elif not should_lock and current['locked'] and current['lock_reason']=='daily':
                await change_lock(context.bot,cid,False,'daily')
        elif not d['daily_lock']:
            current=get_group(cid)
            if current['locked'] and current['lock_reason']=='daily':
                await change_lock(context.bot,cid,False,'daily')
        if get_group(cid)['locked']:continue

        changed=False
        for item in d['announcements']:
            if item.get('enabled',True) is False:continue
            if item.get('skip_shabbat_holiday',False) and (shabbat(now.date()) or yom_tov(now.date())):continue
            if item.get('active_hours'):
                start_h,end_h=item['active_hours']
                hm_now=now.strftime('%H:%M')
                if start_h<=end_h and not (start_h<=hm_now<=end_h):continue
                if start_h>end_h and not (hm_now>=start_h or hm_now<=end_h):continue
            if stamp-int(item.get('last',0))>=int(item.get('minutes',60))*60:
                try:
                    if item.get('delete_previous') and item.get('last_mid'):
                        await safe_delete(context.bot,cid,item['last_mid'])
                    sent=await send_formatted(context.bot,cid,item['text'],markup=buttons(item.get('buttons')),media=item.get('media'))
                    item['last_mid']=sent.message_id if sent else None
                    item['last']=stamp;changed=True;metric(cid,'announcements')
                except TelegramError:log.exception('Announcement send')
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


async def cleanup_slash_commands(update,context):
    """Remove slash-prefixed messages in approved groups; command handlers run first."""
    msg=update.effective_message
    if not msg or not msg.text or not msg.text.startswith('/'):
        return
    g=get_group(msg.chat_id)
    if not g or not g['approved'] or not g.get('active',1):return
    if cfg(msg.chat_id).get('delete_slash_commands',True):
        await safe_delete(context.bot,msg.chat_id,msg.message_id)


def main():
    if not TOKEN:raise RuntimeError('Set BOT_TOKEN in Render environment variables')
    conn().close()
    app=ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('start',start))
    app.add_handler(CommandHandler('admin',owner_panel))
    app.add_handler(CommandHandler('setstart',set_start_text))
    app.add_handler(CommandHandler('showstart',show_start_text))
    app.add_handler(CommandHandler('status',status_cmd))
    app.add_handler(CommandHandler('manage',manage))
    app.add_handler(CommandHandler('register',register_group))
    app.add_handler(CommandHandler('groups',groups_cmd))
    app.add_handler(CommandHandler('cancel',cancel))
    app.add_handler(CommandHandler('skip',panel_skip_handler))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(ChatMemberHandler(my_member,ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & (filters.TEXT|filters.PHOTO|filters.VIDEO) & ~filters.COMMAND,panel_input_handler))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.StatusUpdate.NEW_CHAT_MEMBERS,new_members))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & (filters.StatusUpdate.LEFT_CHAT_MEMBER|filters.StatusUpdate.NEW_CHAT_TITLE|filters.StatusUpdate.NEW_CHAT_PHOTO|filters.StatusUpdate.DELETE_CHAT_PHOTO|filters.StatusUpdate.PINNED_MESSAGE),service))
    group_commands=['reply','warn','warnings','mute','unmute','ban','unban','clean','lock','unlock','allow','unallow','export','import']
    for command in group_commands:app.add_handler(CommandHandler(command,commands,filters=filters.ChatType.GROUPS))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND & ~filters.StatusUpdate.ALL,moderate))
    app.add_handler(MessageHandler(filters.ChatType.GROUPS & filters.TEXT & filters.Regex(r'^/'),cleanup_slash_commands),group=1)
    app.add_error_handler(error_handler)
    if app.job_queue:app.job_queue.run_repeating(periodic,interval=20,first=5,job_kwargs={'max_instances':1,'coalesce':True})
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__=='__main__':main()
