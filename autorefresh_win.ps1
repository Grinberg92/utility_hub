$RepoPath = "C:\VsCodeProj\utility_hub"
$LogFile  = "\\stor-di-2\share2\003_transcode_to_vfx\projects\log.log"

$User = "$env:USERDOMAIN\$env:USERNAME"

$fs = [System.IO.FileStream]::new(
    $LogFile,
    [System.IO.FileMode]::Append,
    [System.IO.FileAccess]::Write,
    [System.IO.FileShare]::ReadWrite
)

$writer = [System.IO.StreamWriter]::new($fs)

try {
    $writer.WriteLine("$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') START | USER: $User")

    Set-Location $RepoPath

    $output = & "C:\Program Files\Git\bin\git.exe" pull origin develop 2>&1
    foreach ($line in $output) {
        $writer.WriteLine($line)
    }

    if ($LASTEXITCODE -ne 0) {
        $writer.WriteLine("ERROR: git command failed with exit code $LASTEXITCODE")
    } else {
        $writer.WriteLine("SUCCESS: git command completed")
    }
}
catch {
    $writer.WriteLine("EXCEPTION: $_")
}
finally {
    $writer.WriteLine("")
    $writer.Flush()
    $writer.Close()
    $fs.Close()
}
