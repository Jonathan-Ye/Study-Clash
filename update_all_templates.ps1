# 批量更新所有模板文件,将.strftime()替换为| strftime_beijing()

$templatesDir = "c:\Users\Joner\Desktop\Study Clash\Study Clash\app\templates"

$replacements = @(
    @(".strftime('%Y-%m-%d %H:%M')", " | strftime_beijing('%Y-%m-%d %H:%M')"),
    @(".strftime('%m-%d %H:%M')", " | strftime_beijing('%m-%d %H:%M')"),
    @(".strftime('%Y-%m-%d %H:%M:%S')", " | strftime_beijing('%Y-%m-%d %H:%M:%S')"),
    @(".strftime('%Y-%m-%d')", " | strftime_beijing('%Y-%m-%d')"),
    @(".strftime('%H:%M:%S')", " | strftime_beijing('%H:%M:%S')"),
    @(".strftime('%m-%d')", " | strftime_beijing('%m-%d')"),
    @(".strftime('%Y-%m-%dT%H:%M')", " | strftime_beijing('%Y-%m-%dT%H:%M')")
)

$count = 0

Get-ChildItem -Path $templatesDir -Recurse -Filter *.html | ForEach-Object {
    $filePath = $_.FullName
    $content = [System.IO.File]::ReadAllText($filePath, [System.Text.Encoding]::UTF8)
    $originalContent = $content
    
    foreach ($replacement in $replacements) {
        $content = $content -replace [regex]::Escape($replacement[0]), $replacement[1]
    }
    
    if ($content -ne $originalContent) {
        [System.IO.File]::WriteAllText($filePath, $content, [System.Text.Encoding]::UTF8)
        Write-Host "Updated: $($_.Name)"
        $count++
    }
}

Write-Host "`nTotal files updated: $count"
