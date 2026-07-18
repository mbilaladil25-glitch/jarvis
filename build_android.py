#!/usr/bin/env python3
"""
JARVIS Android APK Project Generator

Generates a complete Android project that wraps the JARVIS web UI in a WebView
with a splash screen, JavaScript bridge, and proper permissions.

Usage:
    python build_android.py [--output-dir OUTPUT_DIR] [--server-url URL]

After generation, open the project in Android Studio or run:
    cd <output_dir>/JarvisAndroid
    ./gradlew assembleDebug
"""

import argparse
import os
import shutil
from pathlib import Path

DEFAULT_SERVER_URL = "https://YOUR_USERNAME-jarvis-ai.hf.space"
PACKAGE_NAME = "com.jarvis.assistant"
APP_NAME = "J.A.R.V.I.S"
MIN_SDK = 24
TARGET_SDK = 34
COMPILE_SDK = 34
GRADLE_VERSION = "8.2"
AGP_VERSION = "8.2.0"
Q = chr(34)

ICON_CANDIDATES = [
    Path(__file__).resolve().parent.parent / "files" / "jarvis_icon.png",
    Path(__file__).resolve().parent / "jarvis_icon.png",
    Path(__file__).resolve().parent.parent / "jarvis_icon.png",
]

MIPMAP_DENSITIES = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}


def _find_icon():
    for p in ICON_CANDIDATES:
        if p.is_file():
            return p
    return None


def _write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  [write] {path}")


def _copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"  [copy]  {src} -> {dst}")


def _resize_icon(src, dst, size):
    try:
        from PIL import Image
        img = Image.open(src)
        img = img.resize((size, size), Image.LANCZOS)
        dst.parent.mkdir(parents=True, exist_ok=True)
        img.save(dst, "PNG")
        print(f"  [icon]  {dst}  ({size}x{size})")
    except ImportError:
        _copy(src, dst)


# ---------------------------------------------------------------------------
# Content generators - using Q for literal double quotes to avoid escaping hell
# ---------------------------------------------------------------------------
def gen_gradle_wrapper_properties():
    lines = [
        "distributionBase=GRADLE_USER_HOME",
        "distributionPath=wrapper/dists",
        f"distributionUrl=https\\://services.gradle.org/distributions/gradle-{GRADLE_VERSION}-bin.zip",
        "networkTimeout=10000",
        "validateDistributionUrl=true",
        "zipStoreBase=GRADLE_USER_HOME",
        "zipStorePath=wrapper/dists",
        "",
    ]
    return "\n".join(lines)


def gen_gradle_wrapper_script_bat():
    return (
        "@rem Gradle startup script for Windows\n"
        '@if "%DEBUG%"=="" @echo off\n'
        "setlocal\n"
        "set DIRNAME=%~dp0\n"
        'if "%DIRNAME%"=="" set DIRNAME=.\n'
        "@rem Find java.exe\n"
        "set JAVA_EXE=java.exe\n"
        "if defined JAVA_HOME goto findJavaFromJavaHome\n"
        "goto execute\n"
        ":findJavaFromJavaHome\n"
        'set JAVA_HOME=%JAVA_HOME:"=%\n'
        "set JAVA_EXE=%JAVA_HOME%/bin/java.exe\n"
        'if exist "%JAVA_EXE%" goto execute\n'
        "echo ERROR: JAVA_HOME is set to an invalid directory: %JAVA_HOME%\n"
        "goto fail\n"
        ":execute\n"
        '"%JAVA_EXE%" %DEFAULT_JVM_OPTS% %JAVA_OPTS% %GRADLE_OPTS% '
        '"-Dorg.gradle.appname=%APP_BASE_NAME%" '
        '-classpath "%DIRNAME%\\gradle\\wrapper\\gradle-wrapper.jar" '
        "org.gradle.wrapper.GradleWrapperMain %*\n"
        ":end\n"
        "@endlocal\n"
        'if "%ERRORLEVEL%"=="0" goto mainEnd\n'
        ":fail\n"
        "exit /b 1\n"
        ":mainEnd\n"
        "endlocal\n"
    )


def gen_settings_gradle():
    return (
        "pluginManagement {\n"
        "    repositories {\n"
        "        google()\n"
        "        mavenCentral()\n"
        "        gradlePluginPortal()\n"
        "    }\n"
        "}\n"
        "dependencyResolutionManagement {\n"
        "    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)\n"
        "    repositories {\n"
        "        google()\n"
        "        mavenCentral()\n"
        "    }\n"
        "}\n"
        "\n"
        'rootProject.name = "JarvisAndroid"\n'
        "include ':app'\n"
    )


def gen_root_build_gradle():
    return (
        "plugins {\n"
        f"    id 'com.android.application' version '{AGP_VERSION}' apply false\n"
        "}\n"
    )


def gen_app_build_gradle(server_url):
    escaped_url = server_url.replace("\\", "\\\\").replace('"', '\\"')
    return (
        "plugins {\n"
        "    id 'com.android.application'\n"
        "    id 'org.jetbrains.kotlin.android'\n"
        "}\n"
        "\n"
        "android {\n"
        f"    namespace '{PACKAGE_NAME}'\n"
        f"    compileSdk {COMPILE_SDK}\n"
        "\n"
        "    defaultConfig {\n"
        f'        applicationId "{PACKAGE_NAME}"\n'
        f"        minSdk {MIN_SDK}\n"
        f"        targetSdk {TARGET_SDK}\n"
        "        versionCode 1\n"
        f'        versionName "1.0"\n'
        "\n"
        f'        buildConfigField "String", "SERVER_URL", "{Q}{escaped_url}{Q}"\n'
        "    }\n"
        "\n"
        "    buildTypes {\n"
        "        release {\n"
        "            minifyEnabled true\n"
        "            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'\n"
        "        }\n"
        "        debug {\n"
        '            applicationIdSuffix ".debug"\n'
        "            debuggable true\n"
        "        }\n"
        "    }\n"
        "\n"
        "    compileOptions {\n"
        "        sourceCompatibility JavaVersion.VERSION_17\n"
        "        targetCompatibility JavaVersion.VERSION_17\n"
        "    }\n"
        "\n"
        "    packaging {\n"
        "        resources {\n"
        "            excludes += '/META-INF/{AL2.0,LGPL2.1}'\n"
        "        }\n"
        "    }\n"
        "}\n"
        "\n"
        "dependencies {\n"
        "    implementation 'androidx.appcompat:appcompat:1.6.1'\n"
        "    implementation 'com.google.android.material:material:1.11.0'\n"
        "    implementation 'androidx.webkit:webkit:1.9.0'\n"
        "}\n"
    )


def gen_proguard_rules():
    return (
        "# Keep WebView JavaScript interface\n"
        "-keepclassmembers class * {\n"
        "    @android.webkit.JavascriptInterface <methods>;\n"
        "}\n"
        "\n"
        "-keepattributes JavascriptInterface\n"
        "-keepattributes *Annotation*\n"
    )


def gen_manifest():
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n'
        "\n"
        '    <uses-permission android:name="android.permission.INTERNET" />\n'
        '    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />\n'
        '    <uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />\n'
        '    <uses-permission android:name="android.permission.WAKE_LOCK" />\n'
        '    <uses-permission android:name="android.permission.VIBRATE" />\n'
        "\n"
        "    <application\n"
        '        android:allowBackup="true"\n'
        '        android:icon="@mipmap/ic_launcher"\n'
        '        android:roundIcon="@mipmap/ic_launcher_round"\n'
        '        android:label="@string/app_name"\n'
        '        android:supportsRtl="true"\n'
        '        android:theme="@style/Theme.Jarvis"\n'
        '        android:usesCleartextTraffic="true"\n'
        '        android:networkSecurityConfig="@xml/network_security_config">\n'
        "\n"
        '        <activity\n'
        '            android:name=".MainActivity"\n'
        '            android:exported="true"\n'
        '            android:configChanges="orientation|screenSize|keyboardHidden"\n'
        '            android:screenOrientation="portrait"\n'
        '            android:theme="@style/Theme.Jarvis.Splash">\n'
        "            <intent-filter>\n"
        '                <action android:name="android.intent.action.MAIN" />\n'
        '                <category android:name="android.intent.category.LAUNCHER" />\n'
        "            </intent-filter>\n"
        "        </activity>\n"
        "\n"
        "    </application>\n"
        "</manifest>\n"
    )


def gen_network_security_config():
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<network-security-config>\n"
        '    <base-config cleartextTrafficPermitted="false">\n'
        "        <trust-anchors>\n"
        '            <certificates src="system" />\n'
        "        </trust-anchors>\n"
        "    </base-config>\n"
        '    <domain-config cleartextTrafficPermitted="true">\n'
        '        <domain includeSubdomains="true">10.0.2.2</domain>\n'
        '        <domain includeSubdomains="true">localhost</domain>\n'
        "    </domain-config>\n"
        "</network-security-config>\n"
    )


def gen_strings_xml():
    splash_art = (
        "J.A.R.V.I.S\n"
        "\n"
        "     .  .  .   .\n"
        "    .        .       .\n"
        "   .    _____     .   .\n"
        "  .   /      \\  .      .\n"
        " .   |  ___  |  .   .\n"
        "  .  | |   | |  .    .\n"
        "  .  | |___| |  .  .\n"
        "   .  \\_____/  .   .\n"
        "    .       .   .\n"
        "     . . . .   .\n"
        "\n"
        "Just A Rather Very\n"
        "Intelligent System"
    )
    escaped = splash_art.replace('"', '\\"')
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<resources>\n"
        f'    <string name="app_name">{APP_NAME}</string>\n'
        f'    <string name="splash_arc_reactor">{escaped}</string>\n'
        "</resources>\n"
    )


def gen_colors_xml():
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<resources>\n"
        '    <color name="jarvis_blue">#00BFFF</color>\n'
        '    <color name="jarvis_dark_blue">#0A1628</color>\n'
        '    <color name="jarvis_glow">#00D4FF</color>\n'
        '    <color name="jarvis_accent">#1A8CCC</color>\n'
        '    <color name="black">#000000</color>\n'
        '    <color name="white">#FFFFFF</color>\n'
        "</resources>\n"
    )


def gen_themes_xml():
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<resources>\n"
        "\n"
        '    <style name="Theme.Jarvis" parent="Theme.MaterialComponents.DayNight.NoActionBar">\n'
        '        <item name="colorPrimary">@color/jarvis_blue</item>\n'
        '        <item name="colorPrimaryVariant">@color/jarvis_dark_blue</item>\n'
        '        <item name="colorOnPrimary">@color/black</item>\n'
        '        <item name="colorSecondary">@color/jarvis_glow</item>\n'
        '        <item name="colorSecondaryVariant">@color/jarvis_accent</item>\n'
        '        <item name="colorOnSecondary">@color/black</item>\n'
        '        <item name="android:statusBarColor">@color/jarvis_dark_blue</item>\n'
        '        <item name="android:navigationBarColor">@color/jarvis_dark_blue</item>\n'
        '        <item name="android:windowBackground">@color/jarvis_dark_blue</item>\n'
        "    </style>\n"
        "\n"
        '    <style name="Theme.Jarvis.Splash" parent="Theme.Jarvis">\n'
        '        <item name="android:windowFullscreen">true</item>\n'
        '        <item name="android:windowContentOverlay">@null</item>\n'
        "    </style>\n"
        "\n"
        "    <style name=\"JARVIS.Splash.Text\">\n"
        '        <item name="android:fontFamily">monospace</item>\n'
        '        <item name="android:textColor">@color/jarvis_glow</item>\n'
        '        <item name="android:textSize">14sp</item>\n'
        '        <item name="android:gravity">center</item>\n'
        '        <item name="android:lineSpacingExtra">2dp</item>\n'
        "    </style>\n"
        "\n"
        "    <style name=\"JARVIS.Splash.Title\">\n"
        '        <item name="android:fontFamily">monospace</item>\n'
        '        <item name="android:textColor">@color/jarvis_blue</item>\n'
        '        <item name="android:textSize">28sp</item>\n'
        '        <item name="android:textStyle">bold</item>\n'
        '        <item name="android:letterSpacing">0.3</item>\n'
        "    </style>\n"
        "\n"
        "    <style name=\"JARVIS.Splash.Subtitle\">\n"
        '        <item name="android:fontFamily">monospace</item>\n'
        '        <item name="android:textColor">@color/jarvis_glow</item>\n'
        '        <item name="android:textSize">10sp</item>\n'
        '        <item name="android:alpha">0.7</item>\n'
        "    </style>\n"
        "\n"
        "</resources>\n"
    )


def gen_main_activity():
    return (
        "package com.jarvis.assistant;\n"
        "\n"
        "import android.animation.AnimatorSet;\n"
        "import android.animation.ObjectAnimator;\n"
        "import android.annotation.SuppressLint;\n"
        "import android.app.Activity;\n"
        "import android.content.Intent;\n"
        "import android.content.SharedPreferences;\n"
        "import android.graphics.Bitmap;\n"
        "import android.graphics.Color;\n"
        "import android.net.Uri;\n"
        "import android.os.Bundle;\n"
        "import android.os.Handler;\n"
        "import android.os.Looper;\n"
        "import android.view.Gravity;\n"
        "import android.view.View;\n"
        "import android.view.animation.AccelerateDecelerateInterpolator;\n"
        "import android.view.animation.AlphaAnimation;\n"
        "import android.view.animation.Animation;\n"
        "import android.widget.EditText;\n"
        "import android.widget.LinearLayout;\n"
        "import android.widget.ProgressBar;\n"
        "import android.widget.TextView;\n"
        "import android.webkit.ConsoleMessage;\n"
        "import android.webkit.JavascriptInterface;\n"
        "import android.webkit.WebChromeClient;\n"
        "import android.webkit.WebResourceError;\n"
        "import android.webkit.WebResourceRequest;\n"
        "import android.webkit.WebSettings;\n"
        "import android.webkit.WebView;\n"
        "import android.webkit.WebViewClient;\n"
        "import androidx.appcompat.app.AlertDialog;\n"
        "import androidx.appcompat.app.AppCompatActivity;\n"
        "\n"
        "public class MainActivity extends AppCompatActivity {\n"
        "\n"
        '    private static final String PREFS_NAME = "jarvis_prefs";\n'
        '    private static final String KEY_SERVER_URL = "server_url";\n'
        "\n"
        "    private WebView webView;\n"
        "    private LinearLayout splashContainer;\n"
        "    private ProgressBar progressBar;\n"
        "    private TextView statusText;\n"
        "    private String serverUrl;\n"
        "\n"
        "    @Override\n"
        "    protected void onCreate(Bundle savedInstanceState) {\n"
        "        super.onCreate(savedInstanceState);\n"
        "\n"
        "        serverUrl = BuildConfig.SERVER_URL;\n"
        "        String savedUrl = getSavedUrl();\n"
        "        if (savedUrl != null && !savedUrl.isEmpty()) {\n"
        "            serverUrl = savedUrl;\n"
        "        }\n"
        "\n"
        "        showSplash();\n"
        "    }\n"
        "\n"
        "    private String getSavedUrl() {\n"
        "        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);\n"
        "        return prefs.getString(KEY_SERVER_URL, null);\n"
        "    }\n"
        "\n"
        "    private void saveUrl(String url) {\n"
        "        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);\n"
        '        prefs.edit().putString(KEY_SERVER_URL, url).apply();\n'
        "    }\n"
        "\n"
        "    private void showSplash() {\n"
        "        LinearLayout root = new LinearLayout(this);\n"
        "        root.setOrientation(LinearLayout.VERTICAL);\n"
        "        root.setGravity(Gravity.CENTER);\n"
        '        root.setBackgroundColor(Color.parseColor("#0A1628"));\n'
        "        root.setPadding(48, 48, 48, 48);\n"
        "\n"
        "        TextView title = new TextView(this);\n"
        '        title.setText("J.A.R.V.I.S");\n'
        "        title.setTextSize(28);\n"
        '        title.setTextColor(Color.parseColor("#00D4FF"));\n'
        "        title.setGravity(Gravity.CENTER);\n"
        "        title.setTypeface(android.graphics.Typeface.MONOSPACE, android.graphics.Typeface.BOLD);\n"
        "        LinearLayout.LayoutParams titleLp = new LinearLayout.LayoutParams(\n"
        "                LinearLayout.LayoutParams.MATCH_PARENT,\n"
        "                LinearLayout.LayoutParams.WRAP_CONTENT);\n"
        "        titleLp.bottomMargin = 32;\n"
        "        title.setLayoutParams(titleLp);\n"
        "\n"
        "        TextView arcReactor = new TextView(this);\n"
        '        arcReactor.setText("\\n"\n'
        '                + "     .  .  .   .\\n"\n'
        '                + "    .        .       .\\n"\n'
        '                + "   .    _____     .   .\\n"\n'
        '                + "  .   /      \\\\  .      .\\n"\n'
        '                + " .   |  ___  |  .   .\\n"\n'
        '                + "  .  | |   | |  .    .\\n"\n'
        '                + "  .  | |___| |  .  .\\n"\n'
        '                + "   .  \\\\_____/  .   .\\n"\n'
        '                + "    .       .   .\\n"\n'
        '                + "     . . . .   .\\n");\n'
        "        arcReactor.setTextSize(11);\n"
        '        arcReactor.setTextColor(Color.parseColor("#00D4FF"));\n'
        "        arcReactor.setGravity(Gravity.CENTER);\n"
        "        arcReactor.setTypeface(android.graphics.Typeface.MONOSPACE);\n"
        "        LinearLayout.LayoutParams arcLp = new LinearLayout.LayoutParams(\n"
        "                LinearLayout.LayoutParams.MATCH_PARENT,\n"
        "                LinearLayout.LayoutParams.WRAP_CONTENT);\n"
        "        arcLp.bottomMargin = 24;\n"
        "        arcReactor.setLayoutParams(arcLp);\n"
        "\n"
        "        TextView subtitle = new TextView(this);\n"
        '        subtitle.setText("Just A Rather Very Intelligent System");\n'
        "        subtitle.setTextSize(10);\n"
        '        subtitle.setTextColor(Color.parseColor("#00D4FF"));\n'
        "        subtitle.setAlpha(0.7f);\n"
        "        subtitle.setGravity(Gravity.CENTER);\n"
        "        subtitle.setTypeface(android.graphics.Typeface.MONOSPACE);\n"
        "        LinearLayout.LayoutParams subLp = new LinearLayout.LayoutParams(\n"
        "                LinearLayout.LayoutParams.MATCH_PARENT,\n"
        "                LinearLayout.LayoutParams.WRAP_CONTENT);\n"
        "        subLp.bottomMargin = 48;\n"
        "        subtitle.setLayoutParams(subLp);\n"
        "\n"
        "        progressBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);\n"
        "        LinearLayout.LayoutParams pbLp = new LinearLayout.LayoutParams(\n"
        "                LinearLayout.LayoutParams.MATCH_PARENT,\n"
        "                LinearLayout.LayoutParams.WRAP_CONTENT);\n"
        "        pbLp.bottomMargin = 16;\n"
        "        progressBar.setLayoutParams(pbLp);\n"
        "        progressBar.setIndeterminate(true);\n"
        "        progressBar.getIndeterminateDrawable().setColorFilter(\n"
        '                Color.parseColor("#00BFFF"), android.graphics.PorterDuff.Mode.SRC_IN);\n'
        "\n"
        "        statusText = new TextView(this);\n"
        '        statusText.setText("Initializing systems...");\n'
        "        statusText.setTextSize(12);\n"
        '        statusText.setTextColor(Color.parseColor("#00BFFF"));\n'
        "        statusText.setAlpha(0.8f);\n"
        "        statusText.setGravity(Gravity.CENTER);\n"
        "        statusText.setTypeface(android.graphics.Typeface.MONOSPACE);\n"
        "\n"
        "        root.addView(title);\n"
        "        root.addView(arcReactor);\n"
        "        root.addView(subtitle);\n"
        "        root.addView(progressBar);\n"
        "        root.addView(statusText);\n"
        "\n"
        "        splashContainer = root;\n"
        "        setContentView(splashContainer);\n"
        "\n"
        '        ObjectAnimator fadeIn = ObjectAnimator.ofFloat(title, "alpha", 0f, 1f);\n'
        "        fadeIn.setDuration(1000);\n"
        "        fadeIn.setInterpolator(new AccelerateDecelerateInterpolator());\n"
        "\n"
        '        ObjectAnimator arcFade = ObjectAnimator.ofFloat(arcReactor, "alpha", 0f, 1f);\n'
        "        arcFade.setDuration(1500);\n"
        "        arcFade.setInterpolator(new AccelerateDecelerateInterpolator());\n"
        "\n"
        "        AnimatorSet set = new AnimatorSet();\n"
        "        set.playTogether(fadeIn, arcFade);\n"
        "        set.start();\n"
        "\n"
        "        animateStatus();\n"
        "\n"
        "        new Handler(Looper.getMainLooper()).postDelayed(this::promptForUrl, 2500);\n"
        "    }\n"
        "\n"
        "    private void animateStatus() {\n"
        "        String[] messages = {\n"
        '            "Initializing systems...",\n'
        '            "Loading neural interface...",\n'
        '            "Connecting to JARVIS core...",\n'
        '            "Establishing secure link...",\n'
        '            "Systems online."\n'
        "        };\n"
        "        final Handler handler = new Handler(Looper.getMainLooper());\n"
        "        final int[] index = {0};\n"
        "        Runnable animate = new Runnable() {\n"
        "            @Override\n"
        "            public void run() {\n"
        "                if (index[0] < messages.length) {\n"
        "                    AlphaAnimation fadeOut = new AlphaAnimation(1f, 0f);\n"
        "                    fadeOut.setDuration(200);\n"
        "                    fadeOut.setAnimationListener(new Animation.AnimationListener() {\n"
        "                        @Override\n"
        "                        public void onAnimationStart(Animation animation) {}\n"
        "                        @Override\n"
        "                        public void onAnimationEnd(Animation animation) {\n"
        "                            statusText.setText(messages[index[0]]);\n"
        "                            index[0]++;\n"
        "                            AlphaAnimation fadeIn = new AlphaAnimation(0f, 1f);\n"
        "                            fadeIn.setDuration(200);\n"
        "                            statusText.startAnimation(fadeIn);\n"
        "                            if (index[0] < messages.length) {\n"
        "                                handler.postDelayed(this, 400);\n"
        "                            }\n"
        "                        }\n"
        "                        @Override\n"
        "                        public void onAnimationRepeat(Animation animation) {}\n"
        "                    });\n"
        "                    statusText.startAnimation(fadeOut);\n"
        "                }\n"
        "            }\n"
        "        };\n"
        "        handler.postDelayed(animate, 300);\n"
        "    }\n"
        "\n"
        "    private void promptForUrl() {\n"
        "        EditText input = new EditText(this);\n"
        "        input.setText(serverUrl);\n"
        '        input.setHint("https://your-username-jarvis.hf.space");\n'
        '        input.setTextColor(Color.parseColor("#00D4FF"));\n'
        '        input.setHintTextColor(Color.parseColor("#666666"));\n'
        "        input.setTypeface(android.graphics.Typeface.MONOSPACE);\n"
        '        input.setBackgroundColor(Color.parseColor("#0D1F3C"));\n'
        "        input.setPadding(32, 24, 32, 24);\n"
        "        input.setSelectAllOnFocus(true);\n"
        "\n"
        "        LinearLayout container = new LinearLayout(this);\n"
        "        container.setOrientation(LinearLayout.VERTICAL);\n"
        '        container.setBackgroundColor(Color.parseColor("#0A1628"));\n'
        "        int pad = (int) (getResources().getDisplayMetrics().density * 16);\n"
        "        container.setPadding(pad, pad, pad, pad);\n"
        "\n"
        "        TextView label = new TextView(this);\n"
        '        label.setText("Enter JARVIS Server URL:");\n'
        '        label.setTextColor(Color.parseColor("#00D4FF"));\n'
        "        label.setTypeface(android.graphics.Typeface.MONOSPACE);\n"
        "        label.setPadding(0, 0, 0, 12);\n"
        "        container.addView(label);\n"
        "        container.addView(input);\n"
        "\n"
        "        new AlertDialog.Builder(this, android.R.style.Theme_Material_Dialog_Alert)\n"
        "                .setView(container)\n"
        "                .setCancelable(false)\n"
        '                .setPositiveButton("Connect", (dialog, which) -> {\n'
        "                    String url = input.getText().toString().trim();\n"
        "                    if (!url.isEmpty()) {\n"
        "                        serverUrl = url;\n"
        "                        saveUrl(url);\n"
        "                    }\n"
        "                    initWebView();\n"
        "                })\n"
        '                .setNegativeButton("Use Default", (dialog, which) -> {\n'
        "                    initWebView();\n"
        "                })\n"
        "                .show();\n"
        "    }\n"
        "\n"
        "    @SuppressLint(\"SetJavaScriptEnabled\")\n"
        "    private void initWebView() {\n"
        "        webView = new WebView(this);\n"
        "        setContentView(webView);\n"
        "\n"
        "        WebSettings settings = webView.getSettings();\n"
        "        settings.setJavaScriptEnabled(true);\n"
        "        settings.setDomStorageEnabled(true);\n"
        "        settings.setAllowFileAccess(true);\n"
        "        settings.setAllowContentAccess(true);\n"
        "        settings.setCacheMode(WebSettings.LOAD_DEFAULT);\n"
        "        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);\n"
        "        settings.setMediaPlaybackRequiresUserGesture(false);\n"
        "        settings.setLoadWithOverviewMode(true);\n"
        "        settings.setUseWideViewPort(true);\n"
        "\n"
        "        webView.addJavascriptInterface(new JarvisBridge(), \"AndroidBridge\");\n"
        "\n"
        "        webView.setWebViewClient(new WebViewClient() {\n"
        "            @Override\n"
        "            public void onPageStarted(WebView view, String url, Bitmap favicon) {\n"
        "                super.onPageStarted(view, url, favicon);\n"
        "            }\n"
        "\n"
        "            @Override\n"
        "            public void onPageFinished(WebView view, String url) {\n"
        "                super.onPageFinished(view, url);\n"
        "                injectStyles(view);\n"
        "            }\n"
        "\n"
        "            @Override\n"
        "            public void onReceivedError(WebView view, WebResourceRequest request,\n"
        "                                         WebResourceError error) {\n"
        "                super.onReceivedError(view, request, error);\n"
        "                if (request.isForMainFrame()) {\n"
        "                    view.post(() -> {\n"
        "                        view.loadData(getErrorHtml(error.getDescription().toString()),\n"
        "                                \"text/html\", \"UTF-8\");\n"
        "                    });\n"
        "                }\n"
        "            }\n"
        "        });\n"
        "\n"
        "        webView.setWebChromeClient(new WebChromeClient() {\n"
        "            @Override\n"
        "            public boolean onConsoleMessage(ConsoleMessage consoleMessage) {\n"
        "                return true;\n"
        "            }\n"
        "        });\n"
        "\n"
        "        webView.loadUrl(serverUrl);\n"
        "    }\n"
        "\n"
        "    private void injectStyles(WebView view) {\n"
        '        String js = "javascript:(function(){"\n'
        '                + "var s=document.createElement(\'style\');"\n'
        '                + "s.textContent=\'body{-webkit-user-select:none;user-select:none;}\'"\n'
        '                + "+\'@keyframes jarvisPulse{"\n'
        '                + "0%{box-shadow:0 0 5px rgba(0,191,255,0.3);\'"\n'
        '                + "+\'50%{box-shadow:0 0 15px rgba(0,191,255,0.6);\'"\n'
        '                + "+\'100%{box-shadow:0 0 5px rgba(0,191,255,0.3);}}\'"\n'
        '                + "+\'::-webkit-scrollbar{width:4px;\'"\n'
        '                + "+\'::-webkit-scrollbar-thumb{background:#00BFFF;border-radius:2px;}\'"\n'
        '                + "document.head.appendChild(s);"\n'
        '                + "})()";\n'
        "        view.evaluateJavascript(js, null);\n"
        "    }\n"
        "\n"
        "    private String getErrorHtml(String errorMsg) {\n"
        "        return \"<!DOCTYPE html><html><head>\"\n"
        "                + \"<style>\"\n"
        "                + \"body{background:#0A1628;color:#00D4FF;font-family:monospace;\"\n"
        "                + \"display:flex;align-items:center;justify-content:center;\"\n"
        "                + \"flex-direction:column;min-height:100vh;margin:0;text-align:center;}\"\n"
        "                + \"h1{font-size:2em;letter-spacing:0.3em;margin-bottom:0.5em;}\"\n"
        "                + \"p{color:#00BFFF;opacity:0.8;}\"\n"
        "                + \".btn{background:#00BFFF;color:#000;border:none;padding:12px 32px;\"\n"
        "                + \"font-family:monospace;font-size:1em;border-radius:4px;cursor:pointer;\"\n"
        "                + \"margin-top:24px;letter-spacing:0.1em;}\"\n"
        "                + \".btn:active{background:#00D4FF;}\"\n"
        "                + \"</style></head><body>\"\n"
        "                + \"<h1>J.A.R.V.I.S</h1>\"\n"
        "                + \"<p>Connection Error</p>\"\n"
        "                + \"<p style='font-size:0.8em;opacity:0.5;'>\" + errorMsg + \"</p>\"\n"
        "                + \"<button class='btn' onclick='location.reload()'>RETRY</button>\"\n"
        "                + \"</body></html>\";\n"
        "    }\n"
        "\n"
        "    @Override\n"
        "    public void onBackPressed() {\n"
        "        if (webView != null && webView.canGoBack()) {\n"
        "            webView.goBack();\n"
        "        } else {\n"
        "            new AlertDialog.Builder(this)\n"
        '                    .setTitle("Exit JARVIS?")\n'
        '                    .setMessage("Are you sure you want to disconnect?")\n'
        '                    .setPositiveButton("Disconnect", (d, w) -> finish())\n'
        '                    .setNegativeButton("Stay", null)\n'
        "                    .show();\n"
        "        }\n"
        "    }\n"
        "\n"
        "    class JarvisBridge {\n"
        "        @JavascriptInterface\n"
        "        public String getServerUrl() {\n"
        "            return serverUrl;\n"
        "        }\n"
        "\n"
        "        @JavascriptInterface\n"
        "        public void showToast(String message) {\n"
        "            runOnUiThread(() ->\n"
        "                android.widget.Toast.makeText(\n"
        "                    MainActivity.this, message, android.widget.Toast.LENGTH_SHORT\n"
        "                ).show()\n"
        "            );\n"
        "        }\n"
        "\n"
        "        @JavascriptInterface\n"
        "        public void vibrate(int milliseconds) {\n"
        "            android.os.Vibrator v = (android.os.Vibrator)\n"
        "                    getSystemService(ANDROID_VIBRATOR_SERVICE);\n"
        "            if (v != null) {\n"
        "                v.vibrate(android.os.VibrationEffect.createOneShot(\n"
        "                    milliseconds, android.os.VibrationEffect.DEFAULT_AMPLITUDE));\n"
        "            }\n"
        "        }\n"
        "\n"
        "        @JavascriptInterface\n"
        "        public void openUrl(String url) {\n"
        "            runOnUiThread(() -> {\n"
        "                Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));\n"
        "                startActivity(intent);\n"
        "            });\n"
        "        }\n"
        "\n"
        "        @JavascriptInterface\n"
        "        public void reload() {\n"
        "            runOnUiThread(() -> {\n"
        "                if (webView != null) webView.reload();\n"
        "            });\n"
        "        }\n"
        "    }\n"
        "}\n"
    )


def gen_gradle_properties():
    return (
        "org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8\n"
        "android.useAndroidX=true\n"
        "android.nonTransitiveRClass=true\n"
    )


def gen_local_properties():
    return (
        "# This file must *NOT* be checked into Version Control Systems,\n"
        "# as it contains information specific to your local configuration.\n"
        "#\n"
        "# Location of the Android SDK.\n"
        "# sdk.dir=/path/to/android/sdk\n"
    )


def gen_readme(server_url):
    lines = [
        "# J.A.R.V.I.S \u2014 Android App",
        "",
        "Just A Rather Very Intelligent System \u2014 a WebView wrapper for the JARVIS AI",
        "web interface.",
        "",
        "## Prerequisites",
        "",
        "- **Android Studio** (Hedgehog 2023.1+ recommended) or the Android SDK CLI",
        "- JDK 17+",
        "- An Android device or emulator running Android 7.0+ (API 24)",
        "",
        "## Build",
        "",
        "### Option A \u2014 Android Studio",
        "",
        "1. Open this folder in Android Studio.",
        "2. Let Gradle sync finish.",
        "3. **Run > Run 'app'** or press the green play button.",
        "",
        "### Option B \u2014 Command Line",
        "",
        "```bash",
        "# Make sure ANDROID_HOME / ANDROID_SDK_ROOT is set",
        "cd JarvisAndroid",
        "./gradlew assembleDebug        # Linux / macOS",
        "gradlew.bat assembleDebug      # Windows",
        "```",
        "",
        "The debug APK will be at:",
        "`app/build/outputs/apk/debug/app-debug.apk`",
        "",
        "## Configuration",
        "",
        "The server URL defaults to:",
        f"`{server_url}`",
        "",
        "You can change it at runtime through the in-app prompt, or hard-code a",
        "different value by editing `app/build.gradle`:",
        "",
        "```",
        f'buildConfigField "String", "SERVER_URL", "\\"{server_url}\\""',
        "```",
        "",
        "## Customization",
        "",
        "- **Icon**: Place `ic_launcher.png` in each `res/mipmap-*` directory.",
        "- **Splash**: Edit the ASCII art in `MainActivity.java`.",
        "- **Colors**: `res/values/colors.xml`.",
        "",
        "## Architecture",
        "",
        "The app is a single-Activity WebView wrapper:",
        "",
        "| Component | Purpose |",
        "|---|---|",
        "| `MainActivity` | Splash screen, URL prompt, WebView host |",
        "| `JarvisBridge` | `@JavascriptInterface` bridge injected into pages |",
        "| `network_security_config.xml` | Allows cleartext for localhost (dev) |",
        "",
        "## Permissions",
        "",
        "| Permission | Reason |",
        "|---|---|",
        "| `INTERNET` | Load the JARVIS web UI |",
        "| `ACCESS_NETWORK_STATE` | Detect connectivity |",
        "| `WAKE_LOCK` | Keep screen on during sessions |",
        "| `VIBRATE` | Haptic feedback via JS bridge |",
        "",
        "## License",
        "",
        "MIT",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Project assembly
# ---------------------------------------------------------------------------
def generate_project(output_dir, server_url):
    root = output_dir / "JarvisAndroid"
    app = root / "app"
    src = app / "src" / "main"
    java_dir = src / "java" / "com" / "jarvis" / "assistant"
    res = src / "res"

    print(f"\n  Generating JARVIS Android project in: {root}\n")

    # Gradle wrapper
    gw = root / "gradle" / "wrapper"
    _write(gw / "gradle-wrapper.properties", gen_gradle_wrapper_properties())

    gradlew = root / "gradlew"
    gradlew.write_text(
        "#!/bin/sh\nexec java -jar gradle/wrapper/gradle-wrapper.jar \"$@\"\n",
        encoding="utf-8",
    )
    os.chmod(gradlew, 0o755)
    print(f"  [write] {gradlew}")

    _write(root / "gradlew.bat", gen_gradle_wrapper_script_bat())

    # Gradle build files
    _write(root / "settings.gradle", gen_settings_gradle())
    _write(root / "build.gradle", gen_root_build_gradle())
    _write(root / "gradle.properties", gen_gradle_properties())
    _write(root / "local.properties", gen_local_properties())

    # App build
    _write(app / "build.gradle", gen_app_build_gradle(server_url))
    _write(app / "proguard-rules.pro", gen_proguard_rules())

    # Manifest & security
    _write(src / "AndroidManifest.xml", gen_manifest())
    _write(res / "xml" / "network_security_config.xml", gen_network_security_config())

    # Resources
    _write(res / "values" / "strings.xml", gen_strings_xml())
    _write(res / "values" / "colors.xml", gen_colors_xml())
    _write(res / "values" / "themes.xml", gen_themes_xml())

    # Java source
    _write(java_dir / "MainActivity.java", gen_main_activity())

    # Icons
    icon_src = _find_icon()
    if icon_src is not None:
        print(f"\n  Copying icon from: {icon_src}\n")
        for folder, size in MIPMAP_DENSITIES.items():
            _resize_icon(icon_src, res / folder / "ic_launcher.png", size)
            _resize_icon(icon_src, res / folder / "ic_launcher_round.png", size)
    else:
        print("\n  [warn] jarvis_icon.png not found, skipping icon generation\n")
        for folder in MIPMAP_DENSITIES:
            (res / folder).mkdir(parents=True, exist_ok=True)

    # README
    _write(root / "README.md", gen_readme(server_url))

    print(f"\n  Done! Project generated at:\n")
    print(f"    {root}\n")
    print(f"  Next steps:")
    print(f"    1. Open in Android Studio, or")
    print(f"    2. Run:  cd {root} && ./gradlew assembleDebug\n")


def main():
    parser = argparse.ArgumentParser(
        description="Generate a JARVIS Android WebView project"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Directory to create JarvisAndroid/ in (default: script dir)",
    )
    parser.add_argument(
        "--server-url",
        type=str,
        default=DEFAULT_SERVER_URL,
        help=f"JARVIS server URL (default: {DEFAULT_SERVER_URL})",
    )
    args = parser.parse_args()
    generate_project(args.output_dir, args.server_url)


if __name__ == "__main__":
    main()
