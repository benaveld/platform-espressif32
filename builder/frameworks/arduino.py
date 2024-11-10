# Copyright 2014-present PlatformIO <contact@platformio.org>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Arduino

Arduino Wiring-based Framework allows writing cross-platform software to
control devices attached to a wide range of Arduino boards to create all
kinds of creative coding, interactive objects, spaces or physical experiences.

http://arduino.cc/en/Reference/HomePage
"""

import subprocess
import json
import semantic_version
import os
import shutil
from os.path import join

from SCons.Script import COMMAND_LINE_TARGETS, DefaultEnvironment, SConscript
from platformio.package.version import pepver_to_semver
from platformio.project.config import ProjectConfig
from platformio.package.manager.tool import ToolPackageManager

env = DefaultEnvironment()
pm = ToolPackageManager()
platform = env.PioPlatform()
config = env.GetProjectConfig()
board = env.BoardConfig()
mcu = board.get("build.mcu", "esp32")
board_sdkconfig = board.get("espidf.custom_sdkconfig", "")
entry_custom_sdkconfig = "\n"
flag_custom_sdkconfig = False

if config.has_option("env:"+env["PIOENV"], "custom_sdkconfig"):
    entry_custom_sdkconfig = env.GetProjectOption("custom_sdkconfig")
    flag_custom_sdkconfig = True

if len(str(board_sdkconfig)) > 2:
    flag_custom_sdkconfig = True

extra_flags = (''.join([element for element in board.get("build.extra_flags", "")])).replace("-D", " ")
framework_reinstall = False
flag_any_custom_sdkconfig = False

SConscript("_embed_files.py", exports="env")

flag_any_custom_sdkconfig = os.path.exists(join(platform.get_package_dir("framework-arduinoespressif32-libs"),"tools","esp32-arduino-libs","sdkconfig"))

# Esp32-solo1 libs needs adopted settings
if flag_custom_sdkconfig == True and "CORE32SOLO1" in extra_flags and ("CONFIG_FREERTOS_UNICORE=y" in entry_custom_sdkconfig or "CONFIG_FREERTOS_UNICORE=y" in board_sdkconfig):
    if len(str(env.GetProjectOption("build_unflags"))) == 2: # No valid env, needs init
        env['BUILD_UNFLAGS'] = {}
    build_unflags = " ".join(env['BUILD_UNFLAGS'])
    build_unflags = build_unflags + " -mdisable-hardware-atomics -ustart_app_other_cores"
    new_build_unflags = build_unflags.split()
    env.Replace(
      BUILD_UNFLAGS=new_build_unflags
    )

def install_python_deps():
    def _get_installed_pip_packages():
        result = {}
        packages = {}
        pip_output = subprocess.check_output(
            [
                env.subst("$PYTHONEXE"),
                "-m",
                "pip",
                "list",
                "--format=json",
                "--disable-pip-version-check",
            ]
        )
        try:
            packages = json.loads(pip_output)
        except:
            print("Warning! Couldn't extract the list of installed Python packages.")
            return {}
        for p in packages:
            result[p["name"]] = pepver_to_semver(p["version"])

        return result

    deps = {
        "wheel": ">=0.35.1",
        "PyYAML": ">=6.0.2",
        "intelhex": ">=2.3.0"
    }

    installed_packages = _get_installed_pip_packages()
    packages_to_install = []
    for package, spec in deps.items():
        if package not in installed_packages:
            packages_to_install.append(package)
        else:
            version_spec = semantic_version.Spec(spec)
            if not version_spec.match(installed_packages[package]):
                packages_to_install.append(package)

    if packages_to_install:
        env.Execute(
            env.VerboseAction(
                (
                    '"$PYTHONEXE" -m pip install -U '
                    + " ".join(
                        [
                            '"%s%s"' % (p, deps[p])
                            for p in packages_to_install
                        ]
                    )
                ),
                "Installing Arduino Python dependencies",
            )
        )
    return

install_python_deps()

def get_MD5_hash(phrase):
    import hashlib
    return hashlib.md5((phrase).encode('utf-8')).hexdigest()[:16]


def matching_custom_sdkconfig():
    # check if current env is matching to existing sdkconfig
    cust_sdk_is_present = False
    matching_sdkconfig = False
    last_sdkconfig_path = join(env.subst("$PROJECT_DIR"),"sdkconfig.defaults")
    if flag_any_custom_sdkconfig == False:
        matching_sdkconfig = True
        return matching_sdkconfig, cust_sdk_is_present
    if os.path.exists(last_sdkconfig_path) == False:
        return matching_sdkconfig, cust_sdk_is_present
    if flag_custom_sdkconfig == False:
        matching_sdkconfig = False
        return matching_sdkconfig, cust_sdk_is_present
    with open(last_sdkconfig_path) as src:
        line = src.readline()
        if line.startswith("# TASMOTA__"):
            cust_sdk_is_present = True;
            costum_options = entry_custom_sdkconfig
            if (line.split("__")[1]).strip() == get_MD5_hash((costum_options).strip() + mcu):
                matching_sdkconfig = True

    return matching_sdkconfig, cust_sdk_is_present

def check_reinstall_frwrk():
    framework_reinstall = False
    cust_sdk_is_present = False
    matching_sdkconfig = False
    if flag_custom_sdkconfig == True:
        matching_sdkconfig, cust_sdk_is_present = matching_custom_sdkconfig()
    if flag_custom_sdkconfig == False and flag_any_custom_sdkconfig == True:
        # case custom sdkconfig exists and a env without "custom_sdkconfig"
        framework_reinstall = True
    if flag_custom_sdkconfig == True  and matching_sdkconfig == False:
        # check if current custom sdkconfig is different from existing
        framework_reinstall = True
    return framework_reinstall

def call_compile_libs():
    print("*** Compile Arduino IDF libs for %s ***" % env["PIOENV"])
    SConscript("espidf.py")

if check_reinstall_frwrk() == True:
    print("*** Reinstall Arduino framework libs ***")
    shutil.rmtree(platform.get_package_dir("framework-arduinoespressif32-libs"))
    ARDUINO_FRMWRK_LIB_URL = str(platform.get_package_spec("framework-arduinoespressif32-libs")).split("uri=",1)[1][:-1]
    pm.install(ARDUINO_FRMWRK_LIB_URL)
    if flag_custom_sdkconfig == True:
        call_compile_libs()
        flag_custom_sdkconfig = False
    
if flag_custom_sdkconfig == True and flag_any_custom_sdkconfig == False:
    call_compile_libs()

if "arduino" in env.subst("$PIOFRAMEWORK") and "espidf" not in env.subst("$PIOFRAMEWORK") and env.subst("$ARDUINO_LIB_COMPILE_FLAG") in ("Inactive", "True"):
    SConscript(join(platform.get_package_dir("framework-arduinoespressif32"), "tools", "platformio-build.py")))
