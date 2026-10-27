<#
  Live evaluation launcher for the Gemini API FREE TIER (synthetic data only).
  You run this yourself:  powershell -NoProfile -ExecutionPolicy Bypass -File .\run_gemini_live.ps1 [-Model gemini-3.5-flash-lite]

  What it does, in order:
    1. asks for the API key with Read-Host -AsSecureString (typed input is not echoed and not saved
       in PowerShell history);
    2. sets the key and the run settings as environment variables of THIS process only, which the
       Python child inherits; nothing is written to a file, to Git or to the Windows environment;
    3. runs  .venv\Scripts\python.exe -m scripts.live_eval  = SMOKE test: 3 RAG answers + 1 agent task, no
       embeddings, about 7 requests (hard limit 40);
    4. masks the key in any output line, and in a `finally` block restores every variable it touched
       to its previous value, even if the run fails or you press Ctrl+C.

  Only the synthetic catalogue, policies and demo questions in this repository are sent to Google.
  Free-tier content may be used by Google to improve its products. The run stops on quota, model or
  billing errors; it never switches to another model or a paid tier. Do NOT paste the key into the
  chat, a file or the command line.

  -Task embedding-dev: instead of the smoke test, run the B1 embedding experiment
      (python -m scripts.embedding_experiment --run): about 150 texts / 19 embedding requests for the synthetic
      documents, their sentences and the DEV questions (never the holdout); no text generation (LLM_PROVIDER=off);
      hard limits 30 requests and 180 texts; results are cached, so a rerun costs nothing.

  -Task embedding-external -Docs <files> -Questions <file>: the same embedding experiment on documents and questions written by
      an evaluator (see docs/BLIND_EVAL.md). Thresholds are the ones fixed on the dev set, never chosen on these data.
      Reports before-the-gate ranking (top 1/3/5) and after-the-gate safety. About 220 texts / 28 requests for the 28-document,
      124-question trial set; hard limits 45 requests and 260 texts; no text generation; results are cached.

  -SelfTest: no key prompt, no network. Uses a fake key to prove the masking and clean-up logic.
#>
# No positional binding: a stray value (an id after -Only, for example) must be an error, never silently become -Model.
# Lists are written with commas:  -Docs a.json,b.csv   -Only T076,T090
[CmdletBinding(PositionalBinding = $false)]
param([switch]$SelfTest, [string]$Model = 'gemini-3.5-flash-lite', [ValidateSet('smoke', 'embedding-dev', 'embedding-external', 'online-check')][string]$Task = 'smoke',
      [string[]]$Docs = @(), [string]$Questions = '', [string]$Only = '')
$OnlyIds = @($Only -split '[,\s]+' | Where-Object { $_ })

# Only a model NAME is accepted here; app\gemini.py still refuses anything outside its free-tier allowlist.
if ($Model -notmatch '^gemini-[a-z0-9.\-]+$') { Write-Host 'Invalid -Model value.' -ForegroundColor Yellow; exit 2 }

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$names = @('GEMINI_API_KEY', 'LLM_PROVIDER', 'EMBEDDING_PROVIDER', 'GEMINI_MODEL', 'EMBEDDING_MODEL',
           'GEMINI_EMBEDDING_MODEL', 'GEMINI_CONFIRM_FREE_TIER', 'GEMINI_MAX_REQUESTS', 'GEMINI_MAX_EMBED_TEXTS',
           'PYTHONIOENCODING', 'PYTHONWARNINGS', 'PYTHONDONTWRITEBYTECODE')
$isEmbedding = $Task -in @('embedding-dev', 'embedding-external')
$needsFiles = $Task -in @('embedding-external', 'online-check')
$module = if ($isEmbedding) { 'scripts.embedding_experiment' } elseif ($Task -eq 'online-check') { 'scripts.blind_eval' } else { 'scripts.live_eval' }
$moduleFile = ($module -replace '^scripts\.', 'scripts\') + '.py'

# Arguments that follow the python executable for a task. An explicit string[] (never a value that PowerShell can unroll
# into a scalar) so that --run is always passed for the embedding experiment, which refuses to run without it.
function Get-TaskArguments([string]$TaskName, [string[]]$DocFiles = @(), [string]$QuestionsFile = '', [string[]]$OnlyIds = @()) {
    $list = New-Object System.Collections.Generic.List[string]
    $list.Add('-m')
    if ($TaskName -eq 'online-check') {
        $list.Add('scripts.blind_eval'); $list.Add('--online')
        $list.Add('--docs'); foreach ($f in $DocFiles) { $list.Add($f) }
        $list.Add('--questions'); $list.Add($QuestionsFile)
        $list.Add('--out-dir'); $list.Add('reports\blind_online')
        if ($OnlyIds.Count -gt 0) { $list.Add('--only'); foreach ($i in $OnlyIds) { $list.Add($i) } }
    }
    elseif ($TaskName -in @('embedding-dev', 'embedding-external')) {
        $list.Add('scripts.embedding_experiment'); $list.Add('--run')
        if ($TaskName -eq 'embedding-external') {
            $list.Add('--docs'); foreach ($f in $DocFiles) { $list.Add($f) }
            $list.Add('--questions'); $list.Add($QuestionsFile)
        }
    }
    else { $list.Add('scripts.live_eval') }
    return , $list.ToArray()
}
$previous = @{}
foreach ($n in $names) { $previous[$n] = [Environment]::GetEnvironmentVariable($n, 'Process') }
$plain = $null
$exitCode = 1

try {
    if (-not (Test-Path $python)) { throw "Missing $python. Create the project .venv first (see README)." }
    if (-not (Test-Path (Join-Path $root $moduleFile))) { throw "$moduleFile not found." }
    if ($needsFiles) {
        if ($Docs.Count -eq 0 -or [string]::IsNullOrWhiteSpace($Questions)) { throw 'embedding-external needs -Docs <files> and -Questions <file>.' }
        foreach ($f in @($Docs) + @($Questions)) { if (-not (Test-Path $f)) { throw "File not found: $f" } }
    }

    if ($SelfTest) {
        $plain = 'SELFTEST-FAKE-KEY-0123456789abcdef'
        Write-Host '[self-test] fake key, no network.'
    } else {
        Write-Host ''
        Write-Host 'This will send ONLY synthetic catalogue/policy text and demo questions to the Gemini API'
        if ($Task -eq 'embedding-dev') {
            Write-Host '(embedding experiment on DEV questions: about 150 texts / 19 embedding requests, no text generation; hard limit 30 requests).'
        } elseif ($Task -eq 'online-check') {
            Write-Host "(online chatbot check on YOUR files: Gemini embeddings + one generation request per question in -Only ($($OnlyIds.Count) ids); hard limit 60 requests)."
            Write-Host 'The files must be synthetic or otherwise safe to send to Google: free-tier content may be used by the provider.'
        } elseif ($Task -eq 'embedding-external') {
            Write-Host "(embedding experiment on YOUR files $($Docs -join ', ') / ${Questions}: no text generation; hard limits 45 requests, 260 texts)."
            Write-Host 'The files must be synthetic or otherwise safe to send to Google: free-tier content may be used by the provider.'
        } else {
            Write-Host "(smoke test: model $Model only, about 7 requests, nothing is embedded; hard limit 40)."
        }
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
    $env:GEMINI_MODEL = $Model
    $env:EMBEDDING_MODEL = 'gemini-embedding-001'
    $env:GEMINI_EMBEDDING_MODEL = 'gemini-embedding-001'
    $env:GEMINI_CONFIRM_FREE_TIER = 'yes'
    $env:GEMINI_MAX_REQUESTS = '40'
    if ($Task -eq 'online-check') {
        $env:GEMINI_MAX_REQUESTS = '60'       # embeddings of anything not cached + one generation per question asked
        $env:GEMINI_MAX_EMBED_TEXTS = '260'
    }
    if ($isEmbedding) {
        $env:LLM_PROVIDER = 'off'             # embeddings only: no text is generated
        $env:GEMINI_MAX_REQUESTS = if ($Task -eq 'embedding-external') { '45' } else { '30' }
        $env:GEMINI_MAX_EMBED_TEXTS = if ($Task -eq 'embedding-external') { '260' } else { '180' }
    }
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PYTHONWARNINGS = 'ignore'
    $env:PYTHONDONTWRITEBYTECODE = '1'

    Push-Location $root
    try {
        $ErrorActionPreference = 'Continue'   # native stderr must not abort before the key is cleaned up
        if ($SelfTest) {
            & $python -c "import os; print('child sees key:', os.environ['GEMINI_API_KEY'])" 2>&1 |
                ForEach-Object { "$_".Replace($plain, '***') }
            # The command line of each task, as a child process receives it. No module is started, so no network is used.
            foreach ($case in @(@('smoke', 'scripts.live_eval', ''), @('embedding-dev', 'scripts.embedding_experiment', '--run'),
                                @('embedding-external', 'scripts.embedding_experiment', '--run --docs a.csv b.md --questions q.json'),
                                @('online-check', 'scripts.blind_eval', '--online --docs a.csv b.md --questions q.json --out-dir reports\blind_online --only T1 T2'))) {
                [string[]]$taskArgs = Get-TaskArguments $case[0] @('a.csv', 'b.md') 'q.json' @('T1', 'T2')
                $seen = (& $python -c "import sys; print(' '.join(sys.argv[1:]))" @taskArgs 2>&1 | Out-String).Trim()
                $expected = ("-m $($case[1]) $($case[2])").Trim()
                if ($seen -eq $expected) { Write-Host "[self-test] task $($case[0]): arguments '$seen': OK" }
                else { Write-Host "[self-test] task $($case[0]): got '$seen', expected '$expected': FAIL" -ForegroundColor Red }
            }
        } else {
            [string[]]$taskArgs = Get-TaskArguments $Task $Docs $Questions $OnlyIds
            & $python @taskArgs 2>&1 | ForEach-Object { "$_".Replace($plain, '***') }
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
$reportFile = switch ($Task) { 'embedding-dev' { 'reports\b1_embedding_dev.json' } 'embedding-external' { 'reports\b1_embedding_external.json' } 'online-check' { 'reports\blind_online\summary.json' } default { 'reports\live_eval_gemini_smoke.json' } }
if ($exitCode -eq 0) {
    Write-Host "Run finished. Report: $reportFile (contains no key). Tell Claude Code it is ready." -ForegroundColor Green
} else {
    Write-Host "Run ended with exit code $exitCode (stopped early, quota/model/billing error, or cancelled)." -ForegroundColor Yellow
    Write-Host "A partial report may exist in $reportFile; texts already embedded stay cached. Nothing was retried on another model or tier."
}
exit $exitCode
