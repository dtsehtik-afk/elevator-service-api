"""
Patches Android Gradle files after 'cap sync' to fix Kotlin JVM target
compatibility between Capacitor 8 (Java 21) and background-runner (Kotlin 1.8.x).
"""
import re, sys

# 1. Patch variables.gradle
vars_path = 'frontend/android/variables.gradle'
try:
    with open(vars_path) as f:
        content = f.read()
    print(f"=== {vars_path} ===\n{content}\n")
    content = content.replace('VERSION_21', 'VERSION_17')
    with open(vars_path, 'w') as f:
        f.write(content)
    print(f"=== {vars_path} after patch ===\n{content}\n")
except FileNotFoundError:
    print(f"WARNING: {vars_path} not found")

# 2. Patch background-runner build.gradle
bg_path = 'frontend/node_modules/@capacitor/background-runner/android/build.gradle'
try:
    with open(bg_path) as f:
        content = f.read()
    print(f"=== {bg_path} ===\n{content}\n")

    # Add kotlinOptions block inside android { } if not already present
    if 'kotlinOptions' not in content:
        content = content.replace(
            '    lintOptions {',
            '    kotlinOptions {\n        jvmTarget = "17"\n    }\n    lintOptions {'
        )
        print("Added kotlinOptions { jvmTarget = '17' } to android block")

    # Also upgrade kotlin_version default from 1.8.x to 1.9.21
    content = re.sub(
        r"'1\.[89]\.\d+'",
        "'1.9.21'",
        content
    )

    with open(bg_path, 'w') as f:
        f.write(content)
    print(f"=== {bg_path} after patch ===\n{content}\n")
except FileNotFoundError:
    print(f"WARNING: {bg_path} not found")

print("Patch complete.")
