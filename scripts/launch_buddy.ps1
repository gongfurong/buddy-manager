$title = 'Buddy Manager'
$py    = Join-Path $PSScriptRoot 'buddy.py'

Add-Type -TypeDefinition '
using System;
using System.Runtime.InteropServices;
public class BW {
    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    public static extern IntPtr FindWindow(IntPtr c, string t);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
}' -ErrorAction SilentlyContinue

$hwnd = [BW]::FindWindow([IntPtr]::Zero, $title)
if ($hwnd -ne [IntPtr]::Zero) {
    [BW]::ShowWindow($hwnd, 9)
    [BW]::SetForegroundWindow($hwnd)
} else {
    $cmd = "try{`$r=`$host.UI.RawUI;`$s=`$r.WindowSize;if(`$s.Height -lt 36){`$s.Height=36;`$r.WindowSize=`$s}}catch{};python '$py'"
    Start-Process powershell -ArgumentList '-Command', $cmd
}
