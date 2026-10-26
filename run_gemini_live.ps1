<#
  Live evaluation launcher for the Gemini API FREE TIER (synthetic data only).
  You run this yourself:  powershell -NoProfile -ExecutionPolicy Bypass -File .\run_gemini_live.ps1

  What it does, in order:
    1. asks for the API key with Read-Host -AsSecureString (typed input is not echoed and not saved
       in PowerShell history);
    2. sets the key and the run settings as environment variables of THIS process only, which the
       Python child inherits; nothing is written to a file, to Git or to the Windows environment;
    3. runs  .venv\Scripts\python.exe -m scripts.live_eval  (about 25 requests, hard limit 40);
    4. masks the key in any output line, and in a `finally` block restores every variable it touched
       to its previous value, even if the run fails or you press Ctrl+C.

  Only the synthetic catalogue, policies and demo questions in this repository are sent to Google.
  Free-tier content may be used by Google to improve its products. The run stops on quota, model or
  billing errors; it never switches to another model or a paid tier. Do NOT paste the key into the
  chat, a file or the command line.

  -SelfTest: no key prompt, no network. Uses a fake key to prove the masking and clean-up logic.
#>
param([switch]$SelfTest)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$names = @('GEMINI_API_KEY', 'LLM_PROVIDER', 'EMBEDDING_PROVIDER', 'GEMINI_MODEL', 'EMBEDDING_MODEL',
           'GEMINI_EMBEDDING_MODEL', 'GEMINI_CONFIRM_FREE_TIER', 'GEMINI_MAX_REQUESTS', 'PYTHONIOENCODING',
           'PYTHONWARNINGS', 'PYTHONDONTWRITEBYTECODE')
$previous = @{}
foreach ($n in $names) { $previous[$n] = [Environment]::GetEnvironmentVariable($n, 'Process') }
$plain = $null
$exitCode = 1

try {
    if (-not (Test-Path $python)) { throw "Missing $python. Create the project .venv first (see README)." }
    if (-not (Test-Path (Join-Path $root 'scripts\live_eval.py'))) { throw 'scripts\live_eval.py not found.' }

    if ($SelfTest) {
        $plain = 'SELFTEST-FAKE-KEY-0123456789abcdef'
        Write-Host '[self-test] fake key, no network.'
    } else {
        Write-Host ''
        Write-Host 'This will send ONLY synthetic catalogue/policy text and demo questions to the Gemini API'
        Write-Host '(models gemini-2.5-flash and gemini-embedding-001, max 40 requests).'
        Write-Host 'Use a key from a Google AI Studio project that shows "Free Tier" and has NO billing set up.'
        $secure = Read-Host 'Paste the API key (input is hidden)' -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try { $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr); $secure.Dispose() }
        if ([string]::IsNullOrWhiteSpace($plain) -or $plain.Length -lt 20) { throw 'No usable key entered. Nothing was sent.' }
        $answer = Read-Host 'Type YES to confirm: free-tier project without billing, synthetic data only'
        if ($answer -ne 'YES') { throw 'Not confirmed. Nothing was sent.' }
    }

    $env:GEMINI_API_KEY = $plain
    $env:LLM_PROVIDER = 'gemini'
    $env:EMBEDDING_PROVIDER = 'gemini'
    $env:GEMINI_MODEL = 'gemini-2.5-flash'
    $env:EMBEDDING_MODEL = 'gemini-embedding-001'
    $env:GEMINI_EMBEDDING_MODEL = 'gemini-embedding-001'
    $env:GEMINI_CONFIRM_FREE_TIER = 'yes'
    $env:GEMINI_MAX_REQUESTS = '40'
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PYTHONWARNINGS = 'ignore'
    $env:PYTHONDONTWRITEBYTECODE = '1'

    Push-Location $root
    try {
        $ErrorActionPreference = 'Continue'   # native stderr must not abort before the key is cleaned up
        if ($SelfTest) {
            & $python -c "import os; print('child sees key:', os.environ['GEMINI_API_KEY'])" 2>&1 |
                ForEach-Object { "$_".Replace($plain, '***') }
        } else {
            & $python -m scripts.live_eval 2>&1 | ForEach-Object { "$_".Replace($plain, '***') }
        }
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = 'Stop'
        Pop-Location
    }
}
catch {
    $message = "$($_.Exception.Message)"
    if ($plain) { $message = $message.Replace($plain, '***') }
    Write-Host "STOPPED: $message" -ForegroundColor Yellow
}
finally {
    foreach ($n in $names) { [Environment]::SetEnvironmentVariable($n, $previous[$n], 'Process') }
    $plain = $null
    [GC]::Collect()
}

if ($SelfTest) {
    $left = [Environment]::GetEnvironmentVariable('GEMINI_API_KEY', 'Process')
    if ($left -eq $previous['GEMINI_API_KEY']) { Write-Host '[self-test] environment restored: OK' }
    else { Write-Host '[self-test] environment NOT restored: FAIL' -ForegroundColor Red }
    exit 0
}

Write-Host ''
if ($exitCode -eq 0) {
    Write-Host 'Run finished. Report: reports\live_eval_gemini.json (contains no key). Tell Claude Code it is ready.' -ForegroundColor Green
} else {
    Write-Host "Run ended with exit code $exitCode (stopped early, quota/model/billing error, or cancelled)." -ForegroundColor Yellow
    Write-Host 'A partial report may exist in reports\live_eval_gemini.json. Nothing was retried on another model or tier.'
}
exit $exitCode
