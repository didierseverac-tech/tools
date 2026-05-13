@echo off
setlocal enabledelayedexpansion

REM ========================================
REM Script Version Control
REM ========================================
REM Version: 2.0
REM Last Updated: 2026-05-13
REM Changes:
REM   - Added automatic spec file creation if none found
REM   - Searches for .py files and generates default spec
REM   - Improved error handling for missing spec files
REM   - Added build_mode support for onefile and onedir deployment
REM ========================================

echo ========================================
echo PyInstaller Build and Deploy
echo Version 2.0
echo ========================================
echo.

REM =============================
REM Read Configuration from INI
REM =============================
set "CONFIG_FILE=%~dp0deploy_config.ini"
set "PROJECT_DIR=%~dp0"

if not exist "%CONFIG_FILE%" (
    echo ERROR: deploy_config.ini not found!
    pause
    exit /b 1
)

echo Reading configuration...

REM Read INI file line by line
for /f "usebackq delims=" %%a in ("%CONFIG_FILE%") do (
    set "line=%%a"
    call :ParseLine
)

goto :ConfigDone

:ParseLine
REM Skip empty lines
if "!line!"=="" goto :eof

REM Skip comments
if "!line:~0,1!"=="#" goto :eof

REM Skip section headers
if "!line:~0,1!"=="[" goto :eof

REM Find the = sign and parse
set "key="
set "val="
for /f "tokens=1* delims==" %%x in ("!line!") do (
    set "key=%%x"
    set "val=%%y"
)

REM Remove spaces from key
set "key=!key: =!"

REM Remove quotes from value if present
if defined val (
    set "val=!val:"=!"
    REM Trim leading spaces from value only if not empty
    if not "!val!"=="" (
        for /f "tokens=* delims= " %%z in ("!val!") do set "val=%%z"
    )
)

REM Assign to variables - only set project_dir if not empty
if /i "!key!"=="sharepoint_path" set "SHAREPOINT_PATH=!val!"
if /i "!key!"=="build_mode" set "BUILD_MODE=!val!"
if /i "!key!"=="deploy_name" set "DEPLOY_NAME=!val!"
if /i "!key!"=="deploy_folder_name" set "DEPLOY_FOLDER_NAME=!val!"
if /i "!key!"=="contact_email" set "CONTACT_EMAIL=!val!"
if /i "!key!"=="spec_file" set "SPEC_FILE=!val!"
if /i "!key!"=="venv_path" set "VENV_PATH=!val!"
if /i "!key!"=="venv_root" set "VENV_ROOT=!val!"
if /i "!key!"=="venv_name" set "VENV_NAME=!val!"
if /i "!key!"=="project_dir" if not "!val!"=="" set "PROJECT_DIR=!val!"

goto :eof

:ConfigDone

REM Set defaults if not specified or empty
if not defined VENV_ROOT set "VENV_ROOT=C:\PythonProjects\Venv"
if not defined VENV_NAME set "VENV_NAME=Python3_10_11"
if not defined BUILD_MODE set "BUILD_MODE=onefile"
if not defined PROJECT_DIR set "PROJECT_DIR=%~dp0"
if "!PROJECT_DIR!"=="" set "PROJECT_DIR=%~dp0"

if /i not "!BUILD_MODE!"=="onefile" if /i not "!BUILD_MODE!"=="onedir" (
    echo ERROR: build_mode must be onefile or onedir.
    pause
    exit /b 1
)

for %%F in ("!DEPLOY_NAME!") do set "BASE_NAME=%%~nF"
if not defined DEPLOY_FOLDER_NAME set "DEPLOY_FOLDER_NAME=!BASE_NAME!"

if /i "!BUILD_MODE!"=="onedir" (
    set "DEPLOY_TARGET_NAME=!DEPLOY_FOLDER_NAME!"
) else (
    set "DEPLOY_TARGET_NAME=!DEPLOY_NAME!"
)

echo.
echo Configuration loaded:
echo   Virtual Env Root: !VENV_ROOT!
echo   Virtual Env Name: !VENV_NAME!
echo   Build Mode: !BUILD_MODE!
echo   Project Dir: !PROJECT_DIR!
echo   Spec File: !SPEC_FILE!
echo   Deploy Name: !DEPLOY_NAME!
echo   Deploy Folder Name: !DEPLOY_FOLDER_NAME!
echo   SharePoint: !SHAREPOINT_PATH!
echo.

REM =============================
REM Get Version Log Entry (BEFORE building)
REM =============================
echo ========================================
echo Version Log Entry
echo ========================================
echo.
echo Enter a brief description of this version:
echo (Example: Fixed bug in data validation, Added export feature, etc.)
echo.
set /p VERSION_LOG="Version notes: "

if "!VERSION_LOG!"=="" (
    set VERSION_LOG=No description provided
)

echo.
echo Notes saved. Starting build process...
echo.

REM =============================
REM Activate Virtual Environment
REM =============================
echo Activating virtual environment: !VENV_NAME!
if not exist "!VENV_ROOT!\!VENV_NAME!\Scripts\activate.bat" (
    echo ERROR: activate.bat not found for !VENV_NAME! in !VENV_ROOT!.
    echo Please create the environment or adjust configuration.
    pause
    exit /b 1
)

call "!VENV_ROOT!\!VENV_NAME!\Scripts\activate.bat"
if errorlevel 1 (
    echo Failed to activate virtual environment.
    pause
    exit /b 1
)

REM Show Python version
echo.
python -c "import sys;print('Python:',sys.version)" || echo Warning: Python check failed

REM =============================
REM Change to Project Directory
REM =============================
cd /d "!PROJECT_DIR!"
if errorlevel 1 (
    echo Failed to change to project directory !PROJECT_DIR!.
    pause
    exit /b 1
)

REM =============================
REM Check for Spec File or Create Default
REM =============================
echo.
echo Checking for spec file...

if not defined SPEC_FILE (
    echo No spec file specified in config.
    goto :CreateDefaultSpec
)

if not exist "!PROJECT_DIR!\!SPEC_FILE!" (
    echo Spec file !SPEC_FILE! not found in project directory.
    goto :CreateDefaultSpec
) else (
    echo Found spec file: !SPEC_FILE!
    goto :SpecFileReady
)

:CreateDefaultSpec
echo.
echo ========================================
echo Creating Default Spec File
echo ========================================
echo.

REM Find a .py file in the current directory
set "PY_FILE_FOUND="
for %%f in ("!PROJECT_DIR!\*.py") do (
    set "PY_FILE_FOUND=%%~nxf"
    echo Found Python file: %%~nxf
    goto :PyFileFound
)

:PyFileFound
if not defined PY_FILE_FOUND (
    echo ERROR: No .py file found in project directory to create spec file from!
    echo Please either:
    echo   1. Add a .py file to the project directory, or
    echo   2. Create a .spec file manually, or
    echo   3. Specify an existing spec file in deploy_config.ini
    pause
    exit /b 1
)

REM Create default spec file name
for %%f in ("!PY_FILE_FOUND!") do set "BASE_PY_NAME=%%~nf"
set "DEFAULT_SPEC=!BASE_PY_NAME!.spec"
set "SPEC_FILE=!DEFAULT_SPEC!"

echo.
echo Generating spec file from: !PY_FILE_FOUND!
echo Spec file will be: !DEFAULT_SPEC!
echo.

REM Generate spec file using PyInstaller
if /i "!BUILD_MODE!"=="onedir" (
    pyi-makespec "!PY_FILE_FOUND!" --onedir --windowed --name "!BASE_PY_NAME!"
) else (
    pyi-makespec "!PY_FILE_FOUND!" --onefile --windowed --name "!BASE_PY_NAME!"
)

if errorlevel 1 (
    echo.
    echo ERROR: Failed to generate spec file!
    echo Make sure PyInstaller is installed in your virtual environment.
    pause
    exit /b 1
)

echo.
echo Default spec file created successfully: !DEFAULT_SPEC!
echo You can customize this file for future builds.
echo.

:SpecFileReady

REM =============================
REM Clean Previous Build
REM =============================
echo.
echo Cleaning previous build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM =============================
REM Build with PyInstaller
REM =============================
echo.
echo ========================================
echo Building executable from !SPEC_FILE!
echo ========================================
pyinstaller "!SPEC_FILE!" --clean
if errorlevel 1 (
    echo.
    echo ERROR: PyInstaller build failed!
    pause
    exit /b 1
)

echo.
echo Build complete!

REM =============================
REM Find Built Artifact
REM =============================
echo.
if /i "!BUILD_MODE!"=="onedir" (
    echo Locating built application folder...
    set "ARTIFACT_DIR="
    set "ARTIFACT_EXE="
    for /d %%d in ("dist\*") do (
        if exist "%%~fd\*.exe" (
            for %%f in ("%%~fd\*.exe") do (
                set "ARTIFACT_DIR=%%~fd"
                set "ARTIFACT_EXE=%%~ff"
                goto :ArtifactFound
            )
        )
    )
) else (
    echo Locating built executable...
    set "ARTIFACT_EXE="
    for %%f in ("dist\*.exe") do (
        set "ARTIFACT_EXE=%%~ff"
        goto :ArtifactFound
    )
)

:ArtifactFound
if /i "!BUILD_MODE!"=="onedir" (
    if not defined ARTIFACT_DIR (
        echo ERROR: No built application folder found in dist!
        pause
        exit /b 1
    )
    echo Found folder: !ARTIFACT_DIR!
    echo Found launcher: !ARTIFACT_EXE!
) else (
    if not defined ARTIFACT_EXE (
        echo ERROR: No executable found in dist folder!
        pause
        exit /b 1
    )
    echo Found: !ARTIFACT_EXE!
)

REM =============================
REM Archive Old Version
REM =============================
REM Verify SharePoint path exists
if not exist "!SHAREPOINT_PATH!" (
    echo.
    echo ERROR: SharePoint path does not exist:
    echo !SHAREPOINT_PATH!
    pause
    exit /b 1
)

REM Create "Older Versions" folder if it doesn't exist
set "ARCHIVE_PATH=!SHAREPOINT_PATH!\Older Versions"
if not exist "!ARCHIVE_PATH!" (
    echo.
    echo Creating archive folder: Older Versions
    mkdir "!ARCHIVE_PATH!"
)

REM Create timestamped filename for archive
set TIMESTAMP=!date:~-4!!date:~-7,2!!date:~-10,2!_!time:~0,2!!time:~3,2!!time:~6,2!
set TIMESTAMP=!TIMESTAMP: =0!
for %%F in ("!DEPLOY_NAME!") do set "EXT=%%~xF"

REM Archive existing deployment if it exists
if /i "!BUILD_MODE!"=="onedir" (
    if exist "!SHAREPOINT_PATH!\!DEPLOY_FOLDER_NAME!\" (
        echo.
        echo Archiving previous version folder...
        set "ARCHIVE_NAME=!DEPLOY_FOLDER_NAME!_!TIMESTAMP!"
        xcopy "!SHAREPOINT_PATH!\!DEPLOY_FOLDER_NAME!" "!ARCHIVE_PATH!\!ARCHIVE_NAME!\" /E /I /Y >nul

        if errorlevel 1 (
            echo WARNING: Failed to archive old version folder
        ) else (
            echo Archived as: !ARCHIVE_NAME!
        )
    )
) else (
    if exist "!SHAREPOINT_PATH!\!DEPLOY_NAME!" (
        echo.
        echo Archiving previous version...
        set "ARCHIVE_NAME=!BASE_NAME!_!TIMESTAMP!!EXT!"
        copy "!SHAREPOINT_PATH!\!DEPLOY_NAME!" "!ARCHIVE_PATH!\!ARCHIVE_NAME!" /Y >nul

        if errorlevel 1 (
            echo WARNING: Failed to archive old version
        ) else (
            echo Archived as: !ARCHIVE_NAME!
        )
    )
)

REM =============================
REM Deploy to SharePoint
REM =============================
echo.
echo ========================================
echo Deploying to SharePoint
echo ========================================
echo.
if /i "!BUILD_MODE!"=="onedir" (
    echo Source Folder: !ARTIFACT_DIR!
    echo Target Folder: !SHAREPOINT_PATH!\!DEPLOY_FOLDER_NAME!
) else (
    echo Source: !ARTIFACT_EXE!
    echo Target: !SHAREPOINT_PATH!\!DEPLOY_NAME!
)
echo.

if /i "!BUILD_MODE!"=="onedir" (
    echo Copying new version folder...
    if exist "!SHAREPOINT_PATH!\!DEPLOY_FOLDER_NAME!\" rmdir /s /q "!SHAREPOINT_PATH!\!DEPLOY_FOLDER_NAME!"
    xcopy "!ARTIFACT_DIR!" "!SHAREPOINT_PATH!\!DEPLOY_FOLDER_NAME!\" /E /I /Y >nul
) else (
    echo Copying new version...
    copy "!ARTIFACT_EXE!" "!SHAREPOINT_PATH!\!DEPLOY_NAME!" /Y >nul
)

if errorlevel 1 (
    echo.
    echo ERROR: Failed to copy to SharePoint!
    echo Check that you have write permissions.
    pause
    exit /b 1
)


REM =============================
REM Update Single Version Log
REM =============================
set "VERSION_LOG_FILE=!SHAREPOINT_PATH!\!BASE_NAME!_VERSION_LOG.txt"

REM Create log file if it doesn't exist
if not exist "!VERSION_LOG_FILE!" (
    (
        echo ========================================
        echo Version History Log: !BASE_NAME!
        echo ========================================
        echo Deploy Name: !DEPLOY_NAME!
        echo Location: !SHAREPOINT_PATH!
        echo.
        echo Older versions are stored in: Older Versions\
        echo.
        echo ========================================
        echo.
    ) > "!VERSION_LOG_FILE!"
)

REM Append new entry to log
(
    echo [!date! !time!]
    echo Deployed: !DEPLOY_TARGET_NAME!
    if defined ARCHIVE_NAME (
        echo Previous version archived as: !ARCHIVE_NAME!
    ) else (
        echo First deployment
    )
    echo Notes: !VERSION_LOG!
    echo.
    echo ----------------------------------------
    echo.
) >> "!VERSION_LOG_FILE!"

REM =============================
REM Create Desktop Shortcut (if not exists)
REM =============================
set "DESKTOP=%USERPROFILE%\Desktop"
set "SHORTCUT_NAME=!BASE_NAME! SharePoint Location.lnk"
set "SHORTCUT_PATH=!DESKTOP!\!SHORTCUT_NAME!"

if not exist "!SHORTCUT_PATH!" (
    echo.
    echo Creating desktop shortcut to deployment folder...
    
    REM Create VBScript to make shortcut
    set "VBS_SCRIPT=!TEMP!\create_shortcut.vbs"
    (
        echo Set oWS = WScript.CreateObject^("WScript.Shell"^)
        echo sLinkFile = "!SHORTCUT_PATH!"
        echo Set oLink = oWS.CreateShortcut^(sLinkFile^)
        echo oLink.TargetPath = "!SHAREPOINT_PATH!"
        echo oLink.Description = "Shortcut to !BASE_NAME! deployment folder"
        echo oLink.Save
    ) > "!VBS_SCRIPT!"
    
    REM Execute VBScript
    cscript //nologo "!VBS_SCRIPT!"
    
    REM Clean up VBScript
    del "!VBS_SCRIPT!" >nul 2>&1
    
    if exist "!SHORTCUT_PATH!" (
        echo Desktop shortcut created: !SHORTCUT_NAME!
    ) else (
        echo WARNING: Failed to create desktop shortcut
    )
) else (
    echo Desktop shortcut already exists: !SHORTCUT_NAME!
)

echo.
echo ========================================
echo SUCCESS!
echo ========================================
echo.
if /i "!BUILD_MODE!"=="onedir" (
    echo Folder deployed to:
    echo !SHAREPOINT_PATH!\!DEPLOY_FOLDER_NAME!
) else (
    echo File deployed to:
    echo !SHAREPOINT_PATH!\!DEPLOY_NAME!
)
echo.
echo Version log updated:
echo !VERSION_LOG_FILE!
echo.
if defined ARCHIVE_NAME if exist "!ARCHIVE_PATH!\!ARCHIVE_NAME!" (
    echo Previous version archived to:
    echo !ARCHIVE_PATH!\!ARCHIVE_NAME!
    echo.
)

endlocal
pause