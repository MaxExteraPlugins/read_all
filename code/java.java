package com.exteraplugins.read_all;

import android.app.Activity;
import android.app.Application;
import android.content.Context;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.View;
import android.view.ViewGroup;

import java.lang.reflect.Field;
import java.util.HashSet;
import java.util.Set;

import de.robv.android.xposed.XC_MethodHook;
import de.robv.android.xposed.XposedBridge;

import org.telegram.messenger.ApplicationLoader;
import org.telegram.messenger.MessagesStorage;
import org.telegram.messenger.R;
import org.telegram.ui.ActionBar.ActionBar;
import org.telegram.ui.ActionBar.ActionBarMenu;
import org.telegram.ui.ActionBar.ActionBarMenuItem;
import org.telegram.ui.DialogsActivity;

public class Main {
    private static final String TAG = "ReadAll";
    private static final String PREFS = "read_all_prefs";
    private static final int ITEM_ID = 228;
    private static final int[] SCAN_DELAYS = {300, 1000, 2500, 5000, 10000, 20000};

    private static volatile boolean loaded = false;
    private static final Set<XC_MethodHook.Unhook> hooks = new HashSet<>();
    private static volatile Activity currentActivity;
    private static volatile Object clickCallback;
    private static Application.ActivityLifecycleCallbacks activityCallbacks;
    private static Handler handler;
    private static int scanTry = 0;

    public static void load() {
        if (loaded) {
            return;
        }
        loaded = true;
        try {
            registerActivityTracker();
            installHooks();
            scheduleScan(SCAN_DELAYS[0]);
            log("DEX module loaded");
        } catch (Throwable t) {
            loaded = false;
            log("load() error: " + t);
        }
    }

    public static void load(Context context) {
        load();
    }

    public static void unload() {
        try {
            for (XC_MethodHook.Unhook h : hooks) {
                try {
                    h.unhook();
                } catch (Throwable ignored) {
                }
            }
            hooks.clear();
        } catch (Throwable ignored) {
        }
        try {
            if (handler != null) {
                handler.removeCallbacksAndMessages(null);
            }
        } catch (Throwable ignored) {
        }
        try {
            if (activityCallbacks != null && ApplicationLoader.applicationContext instanceof Application) {
                ((Application) ApplicationLoader.applicationContext).unregisterActivityLifecycleCallbacks(activityCallbacks);
            }
        } catch (Throwable ignored) {
        }
        activityCallbacks = null;
        currentActivity = null;
        clickCallback = null;
        handler = null;
        scanTry = 0;
        loaded = false;
    }

    public static void setClickCallback(Object callback) {
        clickCallback = callback;
    }

    public static void pyFlushConfig() {
    }

    public static void pyFlushConfigFull() {
        pyFlushConfig();
    }

    public static void enableActionBar() {
        scanTry = 0;
        scheduleScan(0);
    }

    public static void disableActionBar() {
        try {
            Activity a = currentActivity;
            if (a == null) {
                return;
            }
            ActionBarMenu menu = findMainMenu(a.getWindow().getDecorView());
            if (menu != null) {
                removeFromMenu(menu);
            }
        } catch (Throwable ignored) {
        }
    }

    // ============================================================
    // activity tracking (to reach the current decor view at startup)
    // ============================================================

    private static void registerActivityTracker() {
        try {
            if (activityCallbacks != null) {
                return;
            }
            if (!(ApplicationLoader.applicationContext instanceof Application)) {
                return;
            }
            activityCallbacks = new Application.ActivityLifecycleCallbacks() {
                @Override
                public void onActivityResumed(Activity activity) {
                    currentActivity = activity;
                    scanTry = 0;
                    scanAndInject();
                }

                @Override
                public void onActivityPaused(Activity activity) {
                    if (currentActivity == activity) {
                        currentActivity = null;
                    }
                }

                @Override
                public void onActivityStarted(Activity activity) {
                }

                @Override
                public void onActivityStopped(Activity activity) {
                }

                @Override
                public void onActivitySaveInstanceState(Activity activity, Bundle outState) {
                }

                @Override
                public void onActivityDestroyed(Activity activity) {
                    if (currentActivity == activity) {
                        currentActivity = null;
                    }
                }

                @Override
                public void onActivityCreated(Activity activity, Bundle savedInstanceState) {
                }
            };
            ((Application) ApplicationLoader.applicationContext).registerActivityLifecycleCallbacks(activityCallbacks);
        } catch (Throwable t) {
            log("registerActivityTracker error: " + t);
        }
    }

    // ============================================================
    // hooks - cover every future (re)creation of the main screen
    // ============================================================

    private static void installHooks() {
        try {
            Set<XC_MethodHook.Unhook> set = XposedBridge.hookAllMethods(DialogsActivity.class, "createView", new XC_MethodHook() {
                @Override
                public void afterHookedMethod(MethodHookParam param) {
                    try {
                        injectIntoFragment(param.thisObject);
                    } catch (Throwable ignored) {
                    }
                }
            });
            if (set != null) {
                hooks.addAll(set);
            }
        } catch (Throwable t) {
            log("hook createView error: " + t);
        }

        try {
            Set<XC_MethodHook.Unhook> set = XposedBridge.hookAllMethods(DialogsActivity.class, "onResume", new XC_MethodHook() {
                @Override
                public void afterHookedMethod(MethodHookParam param) {
                    try {
                        injectIntoFragment(param.thisObject);
                    } catch (Throwable ignored) {
                    }
                }
            });
            if (set != null) {
                hooks.addAll(set);
            }
        } catch (Throwable t) {
            log("hook onResume error: " + t);
        }

        try {
            Set<XC_MethodHook.Unhook> set = XposedBridge.hookAllMethods(ActionBar.class, "createMenu", new XC_MethodHook() {
                @Override
                public void afterHookedMethod(MethodHookParam param) {
                    try {
                        Object bar = param.thisObject;
                        if (!(bar instanceof ActionBar)) {
                            return;
                        }
                        Object fragment = getField(bar, "parentFragment");
                        if (!(fragment instanceof DialogsActivity)) {
                            return;
                        }
                        if (!isActionBarEnabled()) {
                            return;
                        }
                        Object menu = param.getResult();
                        if (menu instanceof ActionBarMenu) {
                            injectIntoMenu((ActionBarMenu) menu);
                        }
                    } catch (Throwable ignored) {
                    }
                }
            });
            if (set != null) {
                hooks.addAll(set);
            }
        } catch (Throwable t) {
            log("hook createMenu error: " + t);
        }
    }

    // ============================================================
    // injection
    // ============================================================

    private static void injectIntoFragment(Object fragment) {
        try {
            if (!isActionBarEnabled()) {
                return;
            }
            if (!(fragment instanceof DialogsActivity)) {
                return;
            }
            if (!isMainDialogsFragment(fragment)) {
                return;
            }
            ActionBar bar = ((DialogsActivity) fragment).getActionBar();
            if (bar == null) {
                return;
            }
            ActionBarMenu menu = bar.createMenu();
            if (menu != null) {
                injectIntoMenu(menu);
            }
        } catch (Throwable ignored) {
        }
    }

    private static boolean isMainDialogsFragment(Object fragment) {
        try {
            if (!(fragment instanceof DialogsActivity)) {
                return false;
            }
            DialogsActivity dialogs = (DialogsActivity) fragment;
            try {
                if (dialogs.isArchive()) {
                    return false;
                }
            } catch (Throwable ignored) {
            }
            Object type = getField(fragment, "initialDialogsType");
            if (type instanceof Integer && ((Integer) type).intValue() != 0) {
                return false;
            }
            Object onlySelect = getField(fragment, "onlySelect");
            if (onlySelect instanceof Boolean && ((Boolean) onlySelect).booleanValue()) {
                return false;
            }
            return true;
        } catch (Throwable t) {
            return false;
        }
    }

    private static boolean isActionBarEnabled() {
        try {
            SharedPreferences p = ApplicationLoader.applicationContext.getSharedPreferences(PREFS, 0);
            return p.getBoolean("show_in_actionbar", false);
        } catch (Throwable t) {
            return false;
        }
    }

    private static void injectIntoMenu(ActionBarMenu menu) {
        try {
            if (menu == null) {
                return;
            }
            View existing = menu.findViewById(ITEM_ID);
            if (existing != null) {
                return;
            }
            ActionBarMenuItem item = menu.addItem(ITEM_ID, R.drawable.msg_markread);
            try {
                menu.removeView(item);
            } catch (Throwable ignored) {
            }
            try {
                menu.addView(item, menu.getChildCount() - 1);
            } catch (Throwable ignored) {
            }
            try {
                item.setContentDescription("Read all");
            } catch (Throwable ignored) {
            }
            item.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    handleClick();
                }
            });
            log("actionbar item injected");
        } catch (Throwable t) {
            log("injectIntoMenu error: " + t);
        }
    }

    private static void removeFromMenu(ActionBarMenu menu) {
        try {
            if (menu == null) {
                return;
            }
            View v = menu.findViewById(ITEM_ID);
            if (v != null) {
                menu.removeView(v);
            }
        } catch (Throwable ignored) {
        }
    }

    private static void handleClick() {
        try {
            Object cb = clickCallback;
            if (cb instanceof Runnable) {
                ((Runnable) cb).run();
                return;
            }
            try {
                MessagesStorage.getInstance(0).readAllDialogs(-1);
            } catch (Throwable t) {
                log("fallback readAll error: " + t);
            }
        } catch (Throwable t) {
            log("handleClick error: " + t);
        }
    }

    // ============================================================
    // active scan - covers a main screen already created before
    // the plugin was loaded (fixes the missing button at startup)
    // ============================================================

    private static void scheduleScan(int delayMs) {
        try {
            if (handler == null) {
                handler = new Handler(Looper.getMainLooper());
            }
            handler.postDelayed(new Runnable() {
                @Override
                public void run() {
                    if (scanAndInject()) {
                        scanTry = 0;
                        return;
                    }
                    scanTry++;
                    if (scanTry < SCAN_DELAYS.length) {
                        scheduleScan(SCAN_DELAYS[scanTry]);
                    }
                }
            }, delayMs);
        } catch (Throwable ignored) {
        }
    }

    private static boolean scanAndInject() {
        try {
            if (!isActionBarEnabled()) {
                return false;
            }
            Activity activity = currentActivity;
            if (activity == null) {
                return false;
            }
            View decor = activity.getWindow().getDecorView();
            if (decor == null) {
                return false;
            }
            ActionBarMenu menu = findMainMenu(decor, 0);
            if (menu == null) {
                return false;
            }
            injectIntoMenu(menu);
            return true;
        } catch (Throwable t) {
            return false;
        }
    }

    private static ActionBarMenu findMainMenu(View root) {
        return findMainMenu(root, 0);
    }

    private static ActionBarMenu findMainMenu(View root, int depth) {
        if (root == null || depth > 50) {
            return null;
        }
        if (root instanceof ActionBarMenu) {
            ActionBarMenu menu = (ActionBarMenu) root;
            if (menu.findViewById(ITEM_ID) != null) {
                return menu;
            }
            Object fragment = getMenuFragment(menu);
            if (fragment instanceof DialogsActivity && isMainDialogsFragment(fragment)) {
                return menu;
            }
        }
        if (root instanceof ViewGroup) {
            ViewGroup vg = (ViewGroup) root;
            int n = vg.getChildCount();
            for (int i = 0; i < n; i++) {
                ActionBarMenu res = findMainMenu(vg.getChildAt(i), depth + 1);
                if (res != null) {
                    return res;
                }
            }
        }
        return null;
    }

    private static Object getMenuFragment(ActionBarMenu menu) {
        try {
            View parent = (View) menu.getParent();
            if (!(parent instanceof ActionBar)) {
                return null;
            }
            return getField(parent, "parentFragment");
        } catch (Throwable t) {
            return null;
        }
    }

    private static Object getField(Object obj, String name) {
        try {
            Field f = obj.getClass().getDeclaredField(name);
            f.setAccessible(true);
            return f.get(obj);
        } catch (Throwable t) {
            return null;
        }
    }

    private static void log(String s) {
        Log.d(TAG, s);
    }
}
