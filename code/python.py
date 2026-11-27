from typing import Any, Dict, List

import traceback

from java import dynamic_proxy, jclass
from java.lang import Runnable

from android.os import Handler, Looper
from android.view import View
from android_utils import OnClickListener

from org.telegram.messenger import ApplicationLoader
from org.telegram.ui import DialogsActivity, RightSlidingDialogContainer
from org.telegram.ui.ActionBar import ActionBar

from base_plugin import BasePlugin, MenuItemData, MenuItemType, MethodHook
from client_utils import get_last_fragment, get_messages_storage
from hook_utils import get_private_field
from ui.bulletin import BulletinHelper
from ui.settings import Header, Text, Divider, Switch

__id__ = "read_all"
__name__ = "Read All"
__description__ = "Добавляет кнопку «Прочитать всё»: по нажатию все сообщения помечаются как прочитанные."
__author__ = "@itNotMax - @MaxExteraPlugins"
__version__ = "1.10.4"
__icon__ = "MaxExteraPluginsStickers/0"
__min_version__ = "12.10.6"
__app_version__ = ">=12.1.1"

ITEM_ID = 228
ACTIONBAR_KEY = "show_in_actionbar"
DRAWER_KEY = "show_in_drawer"
SCAN_DELAYS = [300, 1000, 2500, 5000]


def _log_err(plugin_ref, tag):
    try:
        plugin_ref.log(tag + ": " + traceback.format_exc())
    except Exception:
        pass


def _is_dialogs_activity(obj):
    try:
        return obj is not None and obj.getClass().getName() == "org.telegram.ui.DialogsActivity"
    except Exception:
        return False


def _find_declared_method(cls, name):
    try:
        methods = cls.getDeclaredMethods()
        for i in range(len(methods)):
            if methods[i].getName() == name:
                return methods[i]
    except Exception:
        pass
    return None



# ============================================================
# MaxExteraPlugins Shared Author & Channel Subscription Module
# ============================================================

# ============================================================
# MaxExteraPlugins Shared Author & Channel Subscription Module
# ============================================================

# ============================================================
# MaxExteraPlugins Shared Author & Channel Subscription Module
# ============================================================
class AuthorChannelHelper:
    CONFIG_URL = "https://raw.githubusercontent.com/MaxExteraPlugins/config/main/links.json"

    DEFAULT_LINKS = {
        "channel_username": "MaxExteraPlugins",
        "channel_url": "https://t.me/MaxExteraPlugins",
        "header": {"ru": "MaxExteraPlugins", "en": "MaxExteraPlugins"},
        "buttons": [
            {"title": {"ru": "Канал автора", "en": "Author's Channel"}, "icon": "msg_channel", "url": "https://t.me/MaxExteraPlugins"},
            {"title": {"ru": "Поддержать автора", "en": "Support author"}, "icon": "msg_share", "url": "https://t.me/itNotMax"},
            {"title": {"ru": "Сообщить о баге", "en": "Report a bug"}, "icon": "msg_help", "url": "https://t.me/itNotMax"}
        ]
    }

    _TEXTS = {
        "install_card_title": {"ru": "Подпишитесь на канал", "en": "Subscribe to channel"},
        "install_card_msg": {
            "ru": (
                "Мы делаем плагины бесплатными и доступными для всех: пожалуйста, "
                "поддержите нас подпиской на официальный канал @MaxExteraPlugins.\n\n"
                "Там публикуются обновления, важные новости и анонсы новых плагинов."
            ),
            "en": (
                "We keep our plugins free and accessible for everyone: please "
                "support us by subscribing to our official channel @MaxExteraPlugins.\n\n"
                "Updates, news, and new plugin announcements are published there."
            )
        },
        "open_channel_btn": {"ru": "Перейти на канал", "en": "Open channel"},
        "remind_later_btn": {"ru": "Напомнить позже", "en": "Remind later"},
        "never_show_btn": {"ru": "Больше не показывать", "en": "Don't show again"},
        "sub_thank_you": {"ru": "Спасибо за подписку на наш канал!", "en": "Thank you for subscribing to our channel!"},
        "settings_channel": {"ru": "Канал автора", "en": "Author's Channel"},
        "settings_donate": {"ru": "Поддержать автора", "en": "Support author"},
        "settings_bug_report": {"ru": "Сообщить о баге", "en": "Report a bug"}
    }

    @classmethod
    def is_ru(cls) -> bool:
        try:
            from org.telegram.messenger import LocaleController
            lang = str(LocaleController.getInstance().getCurrentLocale().getLanguage() or "").lower()
            return lang in ("ru", "be", "uk", "kk")
        except Exception:
            return True

    @classmethod
    def tr(cls, key: str) -> str:
        entry = cls._TEXTS.get(key, {})
        return entry.get("ru" if cls.is_ru() else "en", entry.get("en", key))

    def __init__(self, plugin, icon_sticker=None):
        self.plugin = plugin
        self.icon_sticker = icon_sticker or getattr(plugin, "__icon__", "MaxExteraPluginsStickers/1")
        self._stopped = False
        self._active_dialog = None

    def on_load(self):
        self._stopped = False
        self._active_dialog = None
        self._load_remote_links_async()
        self._check_initial_subscription_flow()

    def on_event(self, event_type):
        try:
            name = str(event_type).upper()
            if name.endswith("START") or name.endswith("RESUME"):
                if self.is_subscribed() and not self.plugin.get_setting("was_subscribed", False):
                    self.plugin.set_setting("was_subscribed", True)
                    self._dismiss_active_dialog()
                    self._notify_subscribed()
        except Exception:
            pass

    def on_unload(self):
        self._stopped = True
        self._dismiss_active_dialog()

    def is_allowed(self) -> bool:
        return True

    def _get_links(self) -> dict:
        raw = self.plugin.get_setting("remote_links_cache", None)
        if raw:
            try:
                import json
                data = json.loads(raw)
                if isinstance(data, dict): return data
            except Exception:
                pass
        return self.DEFAULT_LINKS

    def _load_remote_links_async(self):
        def worker():
            try:
                import urllib.request, json
                req = urllib.request.Request(self.CONFIG_URL, headers={"User-Agent": "MaxExteraPlugins"})
                with urllib.request.urlopen(req, timeout=4) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        if isinstance(data, dict):
                            self.plugin.set_setting("remote_links_cache", json.dumps(data))
                            self._resolve_channel_in_telegram(data.get("channel_username", "MaxExteraPlugins"))
            except Exception:
                pass
        import threading
        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def _open_url(self, url: str, view=None):
        try:
            from org.telegram.messenger.browser import Browser
            from org.telegram.messenger import ApplicationLoader
            from client_utils import get_last_fragment
            ctx = None
            if view is not None:
                ctx = view.getContext()
            if ctx is None:
                frag = get_last_fragment()
                if frag is not None:
                    ctx = frag.getParentActivity()
            if ctx is None:
                ctx = ApplicationLoader.applicationContext
            Browser.openUrl(ctx, url)
        except Exception:
            pass

    def _resolve_channel_in_telegram(self, username: str):
        try:
            from org.telegram.messenger import UserConfig, MessagesController
            from org.telegram.tgnet import TLRPC, ConnectionsManager, RequestDelegate
            clean_user = username.lstrip("@")
            acc = int(UserConfig.selectedAccount)
            mc = MessagesController.getInstance(acc)
            if not mc: return
            req = TLRPC.TL_contacts_resolveUsername()
            req.username = clean_user
            helper_ref = self
            class Delegate(RequestDelegate):
                def run(self, response, error):
                    if error is None and response is not None:
                        chats = getattr(response, "chats", None)
                        if chats is not None and chats.size() > 0:
                            for a in range(UserConfig.MAX_ACCOUNT_COUNT):
                                try:
                                    if UserConfig.getInstance(a).isClientActivated():
                                        MessagesController.getInstance(a).putChats(chats, False)
                                except Exception:
                                    pass
                            c = chats.get(0)
                            cid = getattr(c, "id", 0)
                            if cid > 0:
                                helper_ref.plugin.set_setting("resolved_channel_id", int(cid))
            ConnectionsManager.getInstance(acc).sendRequest(req, Delegate())
        except Exception:
            pass

    def is_subscribed(self) -> bool:
        try:
            from org.telegram.messenger import UserConfig, MessagesController, MessagesStorage
            from java.lang import Long as JLong
            links = self._get_links()
            target = str(links.get("channel_username", "MaxExteraPlugins") or "MaxExteraPlugins").lower().lstrip("@")
            saved_cid = int(self.plugin.get_setting("resolved_channel_id", 0) or 0)

            for acc in range(UserConfig.MAX_ACCOUNT_COUNT):
                try:
                    uconf = UserConfig.getInstance(acc)
                    if not uconf.isClientActivated():
                        continue

                    mc = MessagesController.getInstance(acc)
                    storage = MessagesStorage.getInstance(acc)

                    # 1. In-memory check by resolved_channel_id
                    if saved_cid and mc is not None:
                        try:
                            c = mc.getChat(JLong(saved_cid))
                            if c is not None:
                                left = bool(getattr(c, "left", True))
                                kicked = bool(getattr(c, "kicked", False))
                                if not left and not kicked:
                                    return True
                        except Exception:
                            pass

                    # 2. In-memory check by username
                    if mc is not None:
                        try:
                            chat = mc.getUserOrChat(target)
                            if chat is not None:
                                cid = int(getattr(chat, "id", 0) or 0)
                                if cid and not saved_cid:
                                    saved_cid = cid
                                    self.plugin.set_setting("resolved_channel_id", cid)
                                left = bool(getattr(chat, "left", True))
                                kicked = bool(getattr(chat, "kicked", False))
                                if not left and not kicked:
                                    return True
                        except Exception:
                            pass

                    # 3. In-memory dialogs check
                    if mc is not None:
                        try:
                            dialog_lists = []
                            d_chan = getattr(mc, "dialogsChannelsOnly", None)
                            if d_chan is not None and d_chan.size() > 0:
                                dialog_lists.append(d_chan)
                            d_all = getattr(mc, "allDialogs", None)
                            if d_all is not None and d_all.size() > 0:
                                dialog_lists.append(d_all)

                            for d_list in dialog_lists:
                                limit = min(d_list.size(), 300)
                                for i in range(limit):
                                    d = d_list.get(i)
                                    did = getattr(d, "id", 0)
                                    if did < 0:
                                        cid = -did
                                        if saved_cid and cid == saved_cid:
                                            c = mc.getChat(JLong(cid))
                                            if c is not None:
                                                left = bool(getattr(c, "left", True))
                                                kicked = bool(getattr(c, "kicked", False))
                                                if not left and not kicked:
                                                    return True
                                        else:
                                            c = mc.getChat(JLong(cid))
                                            if c is not None:
                                                uname = str(getattr(c, "username", "") or "").lower()
                                                if uname == target:
                                                    if not saved_cid:
                                                        saved_cid = cid
                                                        self.plugin.set_setting("resolved_channel_id", cid)
                                                    left = bool(getattr(c, "left", True))
                                                    kicked = bool(getattr(c, "kicked", False))
                                                    if not left and not kicked:
                                                        return True
                        except Exception:
                            pass

                    # 4. Storage check (SQLite on disk)
                    if storage is not None:
                        if saved_cid:
                            try:
                                if storage.containsLocalDialog(JLong(-saved_cid)):
                                    c_sync = storage.getChatSync(JLong(saved_cid))
                                    if c_sync is not None:
                                        left = bool(getattr(c_sync, "left", True))
                                        kicked = bool(getattr(c_sync, "kicked", False))
                                        if not left and not kicked:
                                            return True
                                    else:
                                        return True
                            except Exception:
                                pass

                        try:
                            db = storage.getDatabase()
                            if db is not None:
                                if saved_cid:
                                    try:
                                        cur = db.queryFinalized("SELECT did FROM dialogs WHERE did = ?", [JLong(-saved_cid)])
                                        if cur is not None:
                                            has_row = bool(cur.next())
                                            cur.dispose()
                                            if has_row:
                                                return True
                                    except Exception:
                                        pass

                                try:
                                    cur = db.queryFinalized("SELECT uid, name FROM chats WHERE LOWER(name) LIKE ?", ["%" + target + "%"])
                                    if cur is not None:
                                        while cur.next():
                                            c_id = cur.longValue(0)
                                            if c_id > 0:
                                                if not saved_cid:
                                                    saved_cid = int(c_id)
                                                    self.plugin.set_setting("resolved_channel_id", saved_cid)
                                                cur_d = db.queryFinalized("SELECT did FROM dialogs WHERE did = ?", [JLong(-c_id)])
                                                if cur_d is not None:
                                                    in_dlg = bool(cur_d.next())
                                                    cur_d.dispose()
                                                    if in_dlg:
                                                        cur.dispose()
                                                        return True
                                        cur.dispose()
                                except Exception:
                                    pass
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception:
            pass
        return False

    def prepend_settings(self, original_items=None) -> list:
        from ui.settings import Header, Text, Divider

        if original_items and any(getattr(x, "text", "") == "MaxExteraPlugins" for x in original_items if type(x).__name__ == "Header"):
            return original_items

        links = self._get_links()
        buttons_config = links.get("buttons")

        author_items = []
        if isinstance(buttons_config, list):
            for btn in buttons_config:
                if not isinstance(btn, dict): continue
                raw_url = btn.get("url")
                if isinstance(raw_url, dict):
                    keys = [
                        getattr(self.plugin, "id", None),
                        globals().get("__id__", None),
                        globals().get("__name__", None),
                        self.plugin.__class__.__name__
                    ]
                    keys += [k.lower() for k in keys if isinstance(k, str)]
                    resolved_url = ""
                    for k in keys:
                        if k and k in raw_url:
                            resolved_url = str(raw_url[k] or "").strip()
                            if resolved_url:
                                break
                    url = resolved_url
                elif isinstance(raw_url, str):
                    url = raw_url.strip()
                else:
                    url = ""

                if not url: continue

                title_data = btn.get("title")
                if isinstance(title_data, dict):
                    title = title_data.get("ru" if self.is_ru() else "en") or title_data.get("en") or title_data.get("ru") or ""
                elif isinstance(title_data, str) and title_data:
                    title = title_data
                else:
                    title = btn.get("title_ru" if self.is_ru() else "title_en") or btn.get("title_ru") or btn.get("title_en") or ""

                if not title: continue
                icon = str(btn.get("icon") or "msg_channel").strip()

                def make_click(u):
                    return lambda v=None: self._open_url(u, v)

                author_items.append(Text(text=title, icon=icon, on_click=make_click(url)))
        else:
            for k, text_key, icon_name in [
                ("channel_url", "settings_channel", "msg_channel"),
                ("donate_url", "settings_donate", "msg_share"),
                ("bug_report_url", "settings_bug_report", "msg_help")
            ]:
                u = str(links.get(k) or "").strip()
                if u:
                    author_items.append(Text(text=self.tr(text_key), icon=icon_name, on_click=lambda v=None, target_u=u: self._open_url(target_u, v)))

        res = []
        if author_items:
            hdr = links.get("header") or "MaxExteraPlugins"
            if isinstance(hdr, dict):
                hdr_text = hdr.get("ru" if self.is_ru() else "en") or hdr.get("ru") or hdr.get("en") or "MaxExteraPlugins"
            else:
                hdr_text = str(hdr)
            res.append(Header(text=hdr_text))
            res.extend(author_items)
            res.append(Divider())

        cleaned_items = []
        if original_items:
            skipping_info = False
            for item in original_items:
                item_cls = type(item).__name__
                if item_cls == "Header":
                    txt = str(getattr(item, "text", "") or getattr(item, "title", "") or "").lower()
                    if "информ" in txt or "inform" in txt:
                        skipping_info = True
                        continue
                    else:
                        skipping_info = False
                elif skipping_info and item_cls == "Divider":
                    skipping_info = False
                    continue

                if not skipping_info:
                    cleaned_items.append(item)

        res.extend(cleaned_items)
        return res

    def _dismiss_active_dialog(self):
        try:
            if self._active_dialog is not None:
                self._active_dialog.dismiss()
        except Exception:
            pass
        self._active_dialog = None

    def _is_dialog_active(self) -> bool:
        try:
            if self._active_dialog is not None:
                return bool(self._active_dialog.isShowing())
        except Exception:
            pass
        return False

    def _notify_subscribed(self):
        try:
            from ui.bulletin import BulletinHelper
            BulletinHelper.show_success(self.tr("sub_thank_you"))
        except Exception:
            pass

    def _check_initial_subscription_flow(self):
        def flow():
            try:
                if self.plugin.get_setting("never_show_sub_prompt", False):
                    return

                current_ver = str(getattr(self.plugin, "__version__", globals().get("__version__", "1.0.0")) or "1.0.0")
                last_prompted_ver = self.plugin.get_setting("last_prompted_version", None)

                # Only show on install (last_prompted_ver is None) or update (last_prompted_ver != current_ver)
                if last_prompted_ver is not None and str(last_prompted_ver) == current_ver:
                    return

                if self.is_subscribed():
                    self.plugin.set_setting("last_prompted_version", current_ver)
                    self.plugin.set_setting("was_subscribed", True)
                    return

                self._show_subscription_prompt(current_ver)
            except Exception:
                pass
        from android_utils import run_on_ui_thread
        run_on_ui_thread(flow, 1500)

    def _create_card_content(self, act, title_text, message_text):
        try:
            from android.widget import LinearLayout, TextView, ImageView
            from android.view import Gravity
            from org.telegram.messenger import AndroidUtilities
            from org.telegram.ui.ActionBar import Theme
            from client_utils import create_sticker_drawable

            dp = AndroidUtilities.dp

            layout = LinearLayout(act)
            layout.setOrientation(LinearLayout.VERTICAL)
            layout.setGravity(Gravity.CENTER_HORIZONTAL)
            layout.setPadding(dp(24), dp(20), dp(24), dp(10))

            sticker_drawable = None
            if self.icon_sticker:
                try:
                    sticker_drawable = create_sticker_drawable(self.icon_sticker, dp(120), dp(120))
                except Exception:
                    pass

            if sticker_drawable is not None:
                iv = ImageView(act)
                iv.setImageDrawable(sticker_drawable)
                lp_iv = LinearLayout.LayoutParams(dp(120), dp(120))
                lp_iv.gravity = Gravity.CENTER_HORIZONTAL
                lp_iv.bottomMargin = dp(14)
                layout.addView(iv, lp_iv)

            if title_text:
                tt = TextView(act)
                tt.setText(title_text)
                tt.setTextSize(19.0)
                tt.setTypeface(AndroidUtilities.bold())
                tt.setTextColor(Theme.getColor(Theme.key_dialogTextBlack))
                tt.setGravity(Gravity.CENTER_HORIZONTAL)
                lp_t = LinearLayout.LayoutParams(-1, -2)
                lp_t.bottomMargin = dp(8)
                layout.addView(tt, lp_t)

            if message_text:
                mt = TextView(act)
                mt.setText(message_text)
                mt.setTextSize(15.0)
                mt.setTextColor(Theme.getColor(Theme.key_dialogTextBlack))
                mt.setLineSpacing(float(dp(3)), 1.0)
                mt.setGravity(Gravity.CENTER_HORIZONTAL)
                lp_m = LinearLayout.LayoutParams(-1, -2)
                mt.setLayoutParams(lp_m)
                layout.addView(mt)

            return layout
        except Exception:
            return None

    def _show_subscription_prompt(self, current_ver: str):
        def show():
            try:
                if self._is_dialog_active(): return
                from client_utils import get_last_fragment
                frag = get_last_fragment()
                if not frag: return
                act = frag.getParentActivity()
                if not act: return

                links = self._get_links()
                url = links.get("channel_url", "https://t.me/MaxExteraPlugins")

                from ui.alert import AlertDialogBuilder
                b = AlertDialogBuilder(act)
                content = self._create_card_content(act, self.tr("install_card_title"), self.tr("install_card_msg"))
                if content is not None:
                    b.set_view(content)
                else:
                    b.set_title(self.tr("install_card_title"))
                    b.set_message(self.tr("install_card_msg"))

                def on_open_channel(dialog, which):
                    self._dismiss_active_dialog()
                    self.plugin.set_setting("last_prompted_version", current_ver)
                    self._open_url(url)

                def on_remind_later(dialog, which):
                    self._dismiss_active_dialog()
                    self.plugin.set_setting("last_prompted_version", current_ver)

                def on_never_show(dialog, which):
                    self._dismiss_active_dialog()
                    self.plugin.set_setting("never_show_sub_prompt", True)
                    self.plugin.set_setting("last_prompted_version", current_ver)

                b.set_positive_button(self.tr("open_channel_btn"), on_open_channel)
                b.set_neutral_button(self.tr("remind_later_btn"), on_remind_later)
                b.set_negative_button(self.tr("never_show_btn"), on_never_show)

                def on_dismiss(builder):
                    self.plugin.set_setting("last_prompted_version", current_ver)
                try:
                    b.set_on_dismiss_listener(on_dismiss)
                except Exception:
                    pass

                self._active_dialog = b.show()
                self.plugin.set_setting("last_prompted_version", current_ver)
            except Exception:
                pass
        from android_utils import run_on_ui_thread
        run_on_ui_thread(show)

class ReadAll(BasePlugin):

    def on_app_event(self, event_type):
        if hasattr(self, "_author_helper"):
            self._author_helper.on_event(event_type)

    def on_plugin_load(self):
        self._author_helper = AuthorChannelHelper(self, icon_sticker=globals().get("__icon__", "MaxExteraPluginsStickers/1"))
        self._author_helper.on_load()
        self._unhook_refs = []
        self._scan_index = 0
        self._scan_enabled = False
        self._menu = None
        self._item = None
        self._panel_watch_active = False
        self._watch_rsc = None
        self._install_hooks()
        if self.get_setting(DRAWER_KEY, True):
            self._add_drawer_item()
        if self.get_setting(ACTIONBAR_KEY, False):
            self._start_scan()

    def on_plugin_unload(self):
        if hasattr(self, "_author_helper"):
            self._author_helper.on_unload()
        self._scan_enabled = False
        self._remove_drawer_item()
        for h in getattr(self, "_unhook_refs", []):
            try:
                self.unhook_method(h)
            except Exception:
                pass
        self._unhook_refs.clear()

    # ------------------------------------------------------------
    # hooks
    # ------------------------------------------------------------

    def _keep_unhook(self, uh):
        if uh is None:
            return
        if isinstance(uh, (list, tuple, set)):
            for h in uh:
                if h is not None:
                    self._unhook_refs.append(h)
        else:
            self._unhook_refs.append(uh)

    def _install_hooks(self):
        try:
            dialogs_cls = DialogsActivity.getClass()
            method = _find_declared_method(dialogs_cls, "createView")
            if method is not None:
                self._keep_unhook(self.hook_method(method, ReadAllIconHook(self)))
        except Exception:
            _log_err(self, "READ_ALL-HOOK-CREATEVIEW")
        try:
            dialogs_cls = DialogsActivity.getClass()
            method = _find_declared_method(dialogs_cls, "onResume")
            if method is not None:
                self._keep_unhook(self.hook_method(method, ResumeHook(self)))
        except Exception:
            _log_err(self, "READ_ALL-HOOK-ONRESUME")
        try:
            bar_cls = ActionBar.getClass()
            method = _find_declared_method(bar_cls, "createMenu")
            if method is not None:
                self._keep_unhook(self.hook_method(method, CreateMenuHook(self)))
        except Exception:
            _log_err(self, "READ_ALL-HOOK-CREATEMENU")
        try:
            rsc_cls = RightSlidingDialogContainer.getClass()
            method = _find_declared_method(rsc_cls, "presentFragment")
            if method is not None:
                self._keep_unhook(self.hook_method(method, PresentHook(self)))
        except Exception:
            _log_err(self, "READ_ALL-HOOK-PRESENT")

    # ------------------------------------------------------------
    # injection
    # ------------------------------------------------------------

    def _is_main_dialogs(self, fragment):
        if not _is_dialogs_activity(fragment):
            return False
        try:
            if fragment.isArchive():
                return False
        except Exception:
            pass
        try:
            t = get_private_field(fragment, "initialDialogsType")
            if t is not None and int(t) != 0:
                return False
        except Exception:
            pass
        try:
            s = get_private_field(fragment, "onlySelect")
            if s is not None and bool(s):
                return False
        except Exception:
            pass
        return True

    def _try_inject_fragment(self, fragment):
        try:
            if not self.get_setting(ACTIONBAR_KEY, False):
                return False
            if not self._is_main_dialogs(fragment):
                return False
            action_bar = fragment.getActionBar()
            if action_bar is None:
                return False
            return self._inject_into_menu(action_bar.createMenu())
        except Exception:
            return False

    def _find_item(self, menu):
        if menu is None:
            return None
        n = menu.getChildCount()
        for i in range(n):
            view = menu.getChildAt(i)
            try:
                tag = view.getTag()
            except Exception:
                tag = None
            if tag is None:
                continue
            try:
                if int(tag) == ITEM_ID:
                    return view
            except Exception:
                pass
        return None

    def _place_item(self, menu):
        try:
            n = menu.getChildCount()
            own = -1
            search = -1
            for i in range(n):
                view = menu.getChildAt(i)
                try:
                    tag = view.getTag()
                    if tag is not None and int(tag) == ITEM_ID and own < 0:
                        own = i
                except Exception:
                    pass
                try:
                    if bool(view.isSearchField()) and search < 0:
                        search = i
                except Exception:
                    pass
            if own < 0:
                return
            if search < 0:
                if own == n - 1:
                    return
                view = menu.getChildAt(own)
                menu.removeViewAt(own)
                menu.addView(view, menu.getChildCount() - 1)
                return
            if own == search + 1:
                return
            view = menu.getChildAt(own)
            menu.removeViewAt(own)
            n2 = menu.getChildCount()
            s2 = -1
            for i in range(n2):
                v = menu.getChildAt(i)
                try:
                    if bool(v.isSearchField()):
                        s2 = i
                        break
                except Exception:
                    pass
            if s2 >= 0:
                menu.addView(view, s2 + 1)
            else:
                menu.addView(view, menu.getChildCount())
        except Exception:
            pass

    def _inject_into_menu(self, menu):
        try:
            if menu is None:
                return False
            self._menu = menu
            found = self._find_item(menu)
            if found is not None:
                self._item = found
                self._cleanup_extra_items(menu)
                self._place_item(menu)
                if self._panel_open():
                    found.setVisibility(View.GONE)
                return True
            R_drawable = jclass("org.telegram.messenger.R$drawable")
            item = menu.addItem(ITEM_ID, R_drawable.msg_markread)
            item.setOnClickListener(OnClickListener(lambda v: self._read_all()))
            self._item = item
            self._place_item(menu)
            if self._panel_open():
                item.setVisibility(View.GONE)
            return True
        except Exception:
            return False

    def _cleanup_extra_items(self, menu):
        try:
            if menu is None:
                return
            kept = None
            n = menu.getChildCount()
            for i in range(n - 1, -1, -1):
                view = menu.getChildAt(i)
                try:
                    tag = view.getTag()
                    if tag is not None and int(tag) == ITEM_ID:
                        if kept is None:
                            kept = view
                        else:
                            menu.removeViewAt(i)
                except Exception:
                    pass
        except Exception:
            pass

    def _remove_from_current(self):
        try:
            fragment = get_last_fragment()
            if not _is_dialogs_activity(fragment):
                return
            action_bar = fragment.getActionBar()
            if action_bar is None:
                return
            menu = action_bar.createMenu()
            if menu is None:
                return
            n = menu.getChildCount()
            for i in range(n - 1, -1, -1):
                view = menu.getChildAt(i)
                try:
                    tag = view.getTag()
                    if tag is not None and int(tag) == ITEM_ID:
                        menu.removeViewAt(i)
                except Exception:
                    pass
            self._item = None
            self._menu = None
        except Exception:
            pass

    # ------------------------------------------------------------
    # visibility - hide the item while a side panel (forum chat,
    # search) is open in RightSlidingDialogContainer
    # ------------------------------------------------------------

    def _panel_open(self):
        rsc = getattr(self, "_watch_rsc", None)
        if rsc is None:
            return False
        try:
            return bool(rsc.hasFragment())
        except Exception:
            return False

    def _current_item(self):
        item = getattr(self, "_item", None)
        if item is not None:
            return item
        menu = getattr(self, "_menu", None)
        if menu is not None:
            return self._find_item(menu)
        return None

    def _hide_item(self):
        try:
            item = self._current_item()
            if item is not None:
                item.setVisibility(View.GONE)
        except Exception:
            pass

    def _show_item(self):
        try:
            item = self._current_item()
            if item is not None:
                item.setVisibility(View.VISIBLE)
        except Exception:
            pass

    def _on_panel_opened(self, rsc):
        try:
            self._watch_rsc = rsc
            self._hide_item()
            if self._panel_watch_active:
                return
            self._panel_watch_active = True
            self._watch_panel()
        except Exception:
            pass

    def _watch_panel(self):
        if not self._panel_watch_active:
            return
        try:
            if not bool(self._watch_rsc.hasFragment()):
                self._panel_watch_active = False
                self._watch_rsc = None
                self._show_item()
                return
        except Exception:
            self._panel_watch_active = False
            self._watch_rsc = None
            return
        self._post_delayed(self._watch_panel, 250)

    # ------------------------------------------------------------
    # active scan - covers the main screen already open when the
    # plugin was loaded (the button would otherwise not appear
    # until the screen is recreated)
    # ------------------------------------------------------------

    def _post_delayed(self, fn, ms):
        class _Runnable(dynamic_proxy(Runnable)):
            def run(self_d):
                try:
                    self_d._fn()
                except Exception:
                    pass

        runner = _Runnable()
        runner._fn = fn
        Handler(Looper.getMainLooper()).postDelayed(runner, ms)

    def _start_scan(self):
        self._scan_enabled = True
        self._scan_index = 0
        self._scan_tick()

    def _scan_tick(self):
        if not self._scan_enabled:
            return
        if not self.get_setting(ACTIONBAR_KEY, False):
            return
        fragment = get_last_fragment()
        if self._try_inject_fragment(fragment):
            return
        if self._scan_index < len(SCAN_DELAYS):
            delay = SCAN_DELAYS[self._scan_index]
            self._scan_index += 1
            self._post_delayed(self._scan_tick, delay)

    # ------------------------------------------------------------
    # read all
    # ------------------------------------------------------------

    def _read_all(self):
        try:
            storage = get_messages_storage()
            if storage is None:
                BulletinHelper.show_error("Ошибка: MessagesStorage недоступен")
                return
            storage.readAllDialogs(-1)
            BulletinHelper.show_success("Все чаты прочитаны!")
        except Exception as e:
            BulletinHelper.show_error("Ошибка: " + str(e))

    # ------------------------------------------------------------
    # drawer item
    # ------------------------------------------------------------

    def _add_drawer_item(self):
        try:
            self.add_menu_item(MenuItemData(
                menu_type=MenuItemType.DRAWER_MENU,
                text="Прочитать всё",
                on_click=self._on_read_all_click,
                icon="msg_markread",
                item_id="read_all_drawer_btn"))
        except Exception:
            _log_err(self, "READ_ALL-DRAWER-ADD-ERR")

    def _remove_drawer_item(self):
        try:
            self.remove_menu_item("read_all_drawer_btn")
        except Exception:
            pass

    def _on_read_all_click(self, context: Dict[str, Any]):
        self._read_all()

    def _on_drawer_toggle(self, enabled: bool):
        if enabled:
            self._add_drawer_item()
        else:
            self._remove_drawer_item()

    def _on_actionbar_toggle(self, enabled: bool):
        if enabled:
            self._start_scan()
        else:
            self._scan_enabled = False
            self._remove_from_current()

    def _on_settings_read_all_click(self, view):
        self._read_all()

    # ------------------------------------------------------------
    # settings
    # ------------------------------------------------------------

    def create_settings(self):
        try:
            items = self._inner_create_settings()
        except Exception:
            items = []
        if hasattr(self, '_author_helper'):
            return self._author_helper.prepend_settings(items)
        return items

    def _inner_create_settings(self):
        return [
            Header(text="Выполнить"),
            Text(
                text="Прочитать всё",
                subtext="Пометить все как прочитанные",
                icon="msg_markread",
                on_click=self._on_settings_read_all_click,
            ),
            Divider(),
            Header(text="Отображение кнопки"),
            Switch(
                key=DRAWER_KEY,
                text="Боковое меню",
                default=True,
                subtext="Показать кнопку «Прочитать всё» на боковом меню",
                icon="msg_menu",
                on_change=self._on_drawer_toggle,
            ),
            Switch(
                key=ACTIONBAR_KEY,
                text="Главный экран",
                default=False,
                subtext="Иконка очисти на верхней панели главной страницы",
                icon="msg_header",
                on_change=self._on_actionbar_toggle,
            ),
        ]

# __DEX_BEGIN__
# PLACEHOLDER
# __DEX_END__
