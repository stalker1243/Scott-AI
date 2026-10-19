// Native Windows fixture. It never downloads, removes data or runs Inno Setup.
#include <windows.h>
#include <string>
#include <cstdio>
int wmain(int argc,wchar_t **argv) {
    std::wstring root;bool silent=false,norestart=false;
    for(int i=1;i<argc;++i){std::wstring arg(argv[i]);if(arg.rfind(L"/DIR=",0)==0)root=arg.substr(5);if(arg==L"/VERYSILENT")silent=true;if(arg==L"/NORESTART")norestart=true;}
    if(root.empty() || !silent || !norestart)return 30;
    if(GetFileAttributesW((root+L"/.updater-fixture").c_str())==INVALID_FILE_ATTRIBUTES)return 31;
    const auto exe=root+L"/launcher/ScottAIQt.exe",temporary=root+L"/launcher/fixture-replacement.exe";
    if(!CopyFileW(exe.c_str(),temporary.c_str(),FALSE))return 32;
    // Windows refuses replacement while the old launcher still holds the EXE.
    if(!MoveFileExW(temporary.c_str(),exe.c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))return 33;
    for(const auto *name:{L"Qt6Core.dll",L"Qt6Gui.dll",L"Qt6Network.dll",L"Qt6Widgets.dll"}) {
        const auto source=root+L"/launcher/"+name,copy=source+L".fixture-copy";
        if(!CopyFileW(source.c_str(),copy.c_str(),FALSE) || !MoveFileExW(copy.c_str(),source.c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))return 35;
    }
    FILE *file=_wfopen((root+L"/installed-proof").c_str(),L"wb");if(!file)return 34;
    fputs("old executable released; installation flags accepted",file);fclose(file);return 0;
}
