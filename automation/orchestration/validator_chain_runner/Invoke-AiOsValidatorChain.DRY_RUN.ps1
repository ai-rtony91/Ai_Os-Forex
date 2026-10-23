[CmdletBinding()]
param(
    [string]$ConfigPath = "automation/orchestration/validators/VALIDATOR_CHAIN_CONFIG_001.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-AiOsRepoRoot {
    $root = & git rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($root)) {
        throw "Unable to find git repository root."
    }

    return $root.Trim()
}

function ConvertTo-AiOsRelativePath {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return ""
    }

    return ($Path -replace "\\", "/").TrimStart([char[]]@("/", "."))
}

function Get-AiOsPropertyValue {
    param(
        [object]$InputObject,
        [string[]]$Names,
        [object]$DefaultValue = $null
    )

    foreach ($name in $Names) {
        if ($InputObject.PSObject.Properties.Name -contains $name) {
            return $InputObject.$name
        }
    }

    return $DefaultValue
}

function Get-AiOsScriptForValidator {
    param([string]$ValidatorId)

    switch ($ValidatorId) {
        "execution_registry_guard" { return "automation/orchestration/validators/Invoke-AiOsExecutionRegistryGuard.ps1" }
        "approval_gate" { return "automation/orchestration/validators/Test-ApplyApprovalGate.DRY_RUN.ps1" }
        "commit_package_review" { return "automation/orchestration/validators/Test-CommitPackageManifest.DRY_RUN.ps1" }
        "json_integrity" { return "automation/orchestration/validators/Invoke-OrchestrationValidatorChain.DRY_RUN.ps1" }
        "powershell_syntax" { return "automation/orchestration/validators/Invoke-OrchestrationValidatorChain.DRY_RUN.ps1" }
        "git_clean_state" { return "automation/orchestration/validators/Invoke-OrchestrationValidatorChain.DRY_RUN.ps1" }
        "allowed_paths" { return "automation/orchestration/validators/Invoke-OrchestrationValidatorChain.DRY_RUN.ps1" }
        "blocked_paths" { return "automation/orchestration/validators/Invoke-OrchestrationValidatorChain.DRY_RUN.ps1" }
        "markdown_exists" { return "automation/orchestration/validators/Invoke-OrchestrationValidatorChain.DRY_RUN.ps1" }
        "no_secrets" { return "automation/orchestration/validators/Invoke-OrchestrationValidatorChain.DRY_RUN.ps1" }
        "no_live_trading_enablement" { return "automation/orchestration/validators/Invoke-OrchestrationValidatorChain.DRY_RUN.ps1" }
        "final_git_status" { return "automation/orchestration/validators/Invoke-OrchestrationValidatorChain.DRY_RUN.ps1" }
        default { return "" }
    }
}

function Get-AiOsValidatorArguments {
    param(
        [string]$ValidatorId,
        [string]$ScriptPath,
        [string]$ConfigPath
    )

    $args = @("-NoProfile", "-File", $ScriptPath)

    if ($ScriptPath -like "*Invoke-OrchestrationValidatorChain.DRY_RUN.ps1") {
        $args += @("-ConfigPath", $ConfigPath)
    }

    return $args
}

function ConvertTo-AiOsPreview {
    param([string]$Text)

    if ([string]::IsNullOrEmpty($Text)) {
        return ""
    }

    $normalized = ($Text -replace "\r\n", "`n" -replace "\r", "`n").Trim()
    if ($normalized.Length -le 500) {
        return $normalized
    }

    return $normalized.Substring(0, 500)
}

function Join-AiOsProcessArguments {
    param([string[]]$Arguments)

    # Windows CommandLineToArgv/CRT quoting: double trailing backslashes and
    # backslashes preceding a quote, preserving empty arguments exactly.
    $escaped = foreach ($arg in $Arguments) {
        if ($null -eq $arg) { '""'; continue }
        $value = [regex]::Replace([string]$arg, '(\\*)"', '$1$1\"')
        $value = [regex]::Replace($value, '(\\+)$', '$1$1')
        '"' + $value + '"'
    }
    return ($escaped -join ' ')
}
function Initialize-AiOsOwnedValidatorProcess {
    if ('AiOs.ValidatorProcess' -as [type]) {
        # A fresh source pin cannot replace an older already-loaded CLR type.
        # Refuse the opt-in path below unless its exact overload is present.
        return
    }
    # The host compiler uses its ordinary TEMP location; no evidence or repo files are written.
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

namespace AiOs {
    public class ValidatorProcessApi {
        // Runtime source injection only; JSON never supplies this executable port.
        public virtual bool BeforeResume(ValidatorLaunchWitness emitter, int remainingMilliseconds) { return false; }
        public virtual string GetWorkerObservation() { return ""; }
        public virtual bool Assign(IntPtr job, IntPtr process) { return Native.AssignProcessToJobObject(job, process); }
        public virtual uint Resume(IntPtr thread) { return Native.ResumeThread(thread); }
        public virtual bool Cancel(IntPtr job) { return Native.TerminateJobObject(job, 124); }
        public virtual uint Wait(IntPtr process) { return Native.WaitForSingleObject(process, 0); }
        public virtual bool Accounting(IntPtr job, out uint active) {
            Native.Accounting info;
            bool ok = Native.QueryInformationJobObject(job, 1, out info, (uint)Marshal.SizeOf(typeof(Native.Accounting)), IntPtr.Zero);
            active = info.ActiveProcesses;
            return ok;
        }
    }
    // A launch-bound observation, never an approval or sandbox qualification.
    // API input digests describe the bytes supplied, not a later child memory read.
    public sealed class ValidatorLaunchWitness {
        public string schema = "aios.windows_launch_witness.v1";
        public bool native_admission = false, qualification = false, execution_authority = false;
        public uint creator_process_id, child_process_id;
        public long child_creation_filetime, environment_block_bytes;
        public string actual_image_path = "", application_utf16_sha256 = "", command_line_utf16_sha256 = "";
        public string directory_utf16_sha256 = "", environment_block_utf16_sha256 = "", stdin_utf8_sha256 = "";
        public bool stdin_present, created, assigned_before_resume, resumed;
        public ValidatorLaunchWitness DetachedCopy() { return (ValidatorLaunchWitness)MemberwiseClone(); }
    }
    public class ValidatorProcessResult {
        public bool timed_out, startup_failed, root_exit_confirmed, tree_exit_confirmed, drains_completed;
        public bool retry_allowed;
        public bool observation_required, observation_ready;
        public bool stdin_completed, stdin_writer_joined, stdout_truncated, stderr_truncated;
        public long stdin_bytes_written;
        public int stdin_error_code, stdin_close_error_code;
        public int? exit_code;
        public uint root_process_id;
        public ValidatorLaunchWitness launch_witness;
        public int cleanup_error_code, cancellation_error_code;
        public string stdout = "", stderr = "", cleanup_state = "UNRESOLVED", process_error = "";
    }
    internal static class Native {
        [StructLayout(LayoutKind.Sequential)] internal struct Security { public int Length; public IntPtr Descriptor; public int Inherit; }
        [StructLayout(LayoutKind.Sequential)] internal struct Startup {
            public int Size; public IntPtr Reserved, Desktop, Title;
            public int X, Y, XSize, YSize, XChars, YChars, Fill, Flags;
            public short Show, ReservedSize; public IntPtr ReservedBytes, Input, Output, Error;
        }
        [StructLayout(LayoutKind.Sequential)] internal struct StartupEx { public Startup Info; public IntPtr Attributes; }
        [StructLayout(LayoutKind.Sequential)] internal struct ProcessInfo { public IntPtr Process, Thread; public uint ProcessId, ThreadId; }
        [StructLayout(LayoutKind.Sequential)] internal struct BasicLimits {
            public long ProcessTime, JobTime; public uint Flags; public UIntPtr MinWorking, MaxWorking;
            public uint ActiveLimit; public UIntPtr Affinity; public uint Priority, Scheduling;
        }
        [StructLayout(LayoutKind.Sequential)] internal struct IoCounters { public ulong ReadOps, WriteOps, OtherOps, ReadBytes, WriteBytes, OtherBytes; }
        [StructLayout(LayoutKind.Sequential)] internal struct ExtendedLimits {
            public BasicLimits Basic; public IoCounters Io; public UIntPtr ProcessMemory, JobMemory, PeakProcess, PeakJob;
        }
        [StructLayout(LayoutKind.Sequential)] internal struct Accounting {
            public long User, Kernel, PeriodUser, PeriodKernel; public uint Faults, TotalProcesses, ActiveProcesses, Terminated;
        }
        [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)] internal static extern IntPtr CreateJobObjectW(IntPtr security, string name);
        [DllImport("kernel32.dll", SetLastError=true)] internal static extern bool SetInformationJobObject(IntPtr job, int type, ref ExtendedLimits info, uint size);
        [DllImport("kernel32.dll", SetLastError=true)] internal static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
        [DllImport("kernel32.dll", SetLastError=true)] internal static extern bool TerminateJobObject(IntPtr job, uint code);
        [DllImport("kernel32.dll", SetLastError=true)] internal static extern bool QueryInformationJobObject(IntPtr job, int type, out Accounting info, uint size, IntPtr returned);
        [DllImport("kernel32.dll", SetLastError=true)] internal static extern bool CreatePipe(out IntPtr read, out IntPtr write, ref Security security, uint size);
        [DllImport("kernel32.dll", SetLastError=true)] internal static extern bool SetHandleInformation(IntPtr handle, uint mask, uint flags);
        [DllImport("kernel32.dll", SetLastError=true)] internal static extern bool InitializeProcThreadAttributeList(IntPtr list, int count, uint flags, ref IntPtr size);
        [DllImport("kernel32.dll", SetLastError=true)] internal static extern bool UpdateProcThreadAttribute(IntPtr list, uint flags, IntPtr attribute, IntPtr value, IntPtr size, IntPtr previous, IntPtr returned);
        [DllImport("kernel32.dll")] internal static extern void DeleteProcThreadAttributeList(IntPtr list);
        [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)] internal static extern bool CreateProcessW(string application, StringBuilder command, IntPtr processSecurity, IntPtr threadSecurity, bool inherit, uint flags, IntPtr environment, string directory, ref StartupEx startup, out ProcessInfo process);
        [DllImport("kernel32.dll")] internal static extern uint GetCurrentProcessId();
        [DllImport("kernel32.dll", SetLastError=true)] internal static extern bool GetProcessTimes(IntPtr process, out long creation, out long exit, out long kernel, out long user);
        [DllImport("kernel32.dll", SetLastError=true, CharSet=CharSet.Unicode)] internal static extern bool QueryFullProcessImageNameW(IntPtr process, uint flags, StringBuilder path, ref uint size);
        [DllImport("kernel32.dll", SetLastError=true)] internal static extern uint ResumeThread(IntPtr thread);
        [DllImport("kernel32.dll", SetLastError=true)] internal static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);
        [DllImport("kernel32.dll", SetLastError=true)] internal static extern bool TerminateProcess(IntPtr process, uint code);
        [DllImport("kernel32.dll", SetLastError=true)] internal static extern bool GetExitCodeProcess(IntPtr process, out uint code);
        [DllImport("kernel32.dll", SetLastError=true)] internal static extern bool WriteFile(IntPtr file, byte[] bytes, uint count, out uint written, IntPtr overlapped);
        [DllImport("kernel32.dll", SetLastError=true)] internal static extern bool ReadFile(IntPtr file, byte[] bytes, uint count, out uint read, IntPtr overlapped);
        [DllImport("kernel32.dll", SetLastError=true)] internal static extern IntPtr OpenThread(uint access, bool inherit, uint id);
        [DllImport("kernel32.dll")] internal static extern uint GetCurrentThreadId();
        [DllImport("kernel32.dll", SetLastError=true)] internal static extern bool CancelSynchronousIo(IntPtr thread);
        [DllImport("kernel32.dll", SetLastError=true)] internal static extern bool CloseHandle(IntPtr handle);
    }
    // Reader threads never execute PowerShell and expose partial bytes even on cancellation.
    internal sealed class PipeDrain {
        private readonly IntPtr pipe;
        private readonly Encoding encoding;
        private readonly int retention;
        internal bool Truncated;
        private readonly StringBuilder text = new StringBuilder();
        private readonly Thread thread;
        private readonly ManualResetEvent ready = new ManualResetEvent(false);
        private IntPtr threadHandle;
        private volatile bool stop;
        private bool started;
        internal volatile bool Done;
        internal int Error;
        internal PipeDrain(IntPtr pipe, Encoding encoding, int retention) { this.pipe = pipe; this.encoding = encoding; this.retention = retention; thread = new Thread(Read); thread.IsBackground = true; }
        internal void Start(int wait) {
            thread.Start();
            started = true;
            if (!ready.WaitOne(wait) || threadHandle == IntPtr.Zero) throw new InvalidOperationException("Output reader setup failed.");
        }
        private void Read() {
            try {
                threadHandle = Native.OpenThread(1, false, Native.GetCurrentThreadId());
                if (threadHandle == IntPtr.Zero) { Error = Marshal.GetLastWin32Error(); return; }
                ready.Set();
                byte[] bytes = new byte[4096];
                char[] chars = new char[8192];
                Decoder decoder = encoding.GetDecoder();
                while (!stop) {
                    uint read;
                    if (!Native.ReadFile(pipe, bytes, (uint)bytes.Length, out read, IntPtr.Zero)) {
                        int error = Marshal.GetLastWin32Error();
                        if (error != 109 && !(stop && error == 995)) Error = error;
                        break;
                    }
                    int count = decoder.GetChars(bytes, 0, (int)read, chars, 0, read == 0);
                    lock (text) {
                        int keep = retention == 0 ? count : Math.Min(count, Math.Max(0, retention - text.Length));
                        text.Append(chars, 0, keep);
                        if (keep < count) Truncated = true;
                    }
                    if (read == 0) break;
                }
            }
            catch { Error = -1; }
            finally { Done = true; ready.Set(); }
        }
        internal string Text { get { lock(text) { return text.ToString(); } } }
        internal void Cancel() { stop = true; if (threadHandle != IntPtr.Zero) Native.CancelSynchronousIo(threadHandle); }
        internal bool Join(int wait) { return !started || thread.Join(Math.Max(0, wait)); }
        internal void Dispose() {
            if (threadHandle != IntPtr.Zero) Native.CloseHandle(threadHandle);
            ready.Dispose();
        }
    }
    // This thread owns only its pipe creation handle. It never invokes PowerShell.
    // Cancellation targets this exact thread; disposal follows a bounded join.
    internal sealed class PipeInput {
        private IntPtr pipe, threadHandle;
        private readonly byte[] bytes;
        private readonly Thread thread;
        private readonly ManualResetEvent ready = new ManualResetEvent(false);
        private volatile bool stop;
        private bool started;
        internal volatile bool Done;
        internal int Error, CloseError;
        internal long Written;
        internal PipeInput(IntPtr pipe, byte[] bytes) { this.pipe = pipe; this.bytes = bytes; thread = new Thread(Write); thread.IsBackground = true; }
        internal void Start(int wait) {
            thread.Start(); started = true;
            if (!ready.WaitOne(wait) || threadHandle == IntPtr.Zero) throw new InvalidOperationException("Input writer setup failed.");
        }
        private void ClosePipe() {
            IntPtr owned = Interlocked.Exchange(ref pipe, IntPtr.Zero);
            if (owned != IntPtr.Zero && !Native.CloseHandle(owned)) CloseError = Marshal.GetLastWin32Error();
        }
        private void Write() {
            try {
                threadHandle = Native.OpenThread(1, false, Native.GetCurrentThreadId());
                if (threadHandle == IntPtr.Zero) { Error = Marshal.GetLastWin32Error(); return; }
                ready.Set();
                byte[] chunk = new byte[16384];
                while (!stop && Written < bytes.Length) {
                    int count = Math.Min(chunk.Length, bytes.Length - (int)Written);
                    Buffer.BlockCopy(bytes, (int)Written, chunk, 0, count);
                    uint written;
                    if (!Native.WriteFile(pipe, chunk, (uint)count, out written, IntPtr.Zero)) {
                        Error = Marshal.GetLastWin32Error(); break;
                    }
                    if (written == 0) { Error = -1; break; }
                    Written += written;
                }
            }
            catch { Error = -1; }
            finally { ClosePipe(); Done = true; ready.Set(); }
        }
        internal void Cancel() { stop = true; if (threadHandle != IntPtr.Zero) Native.CancelSynchronousIo(threadHandle); }
        internal bool Join(int wait) { return !started || thread.Join(Math.Max(0, wait)); }
        internal void Dispose() {
            ClosePipe();
            if (threadHandle != IntPtr.Zero && !Native.CloseHandle(threadHandle)) CloseError = Marshal.GetLastWin32Error();
            ready.Dispose();
        }
    }
    public static class ValidatorProcess {
        // Managed-only readiness check; no native call and no qualification.
        public static bool CheckObservationReady(ValidatorProcessApi api, ValidatorLaunchWitness witness, int remainingMilliseconds) {
            if (api == null || witness == null || remainingMilliseconds <= 0 || !witness.created || !witness.assigned_before_resume || witness.resumed || witness.native_admission || witness.qualification || witness.execution_authority || witness.creator_process_id == 0 || witness.child_process_id == 0 || witness.creator_process_id == witness.child_process_id || witness.child_creation_filetime <= 0) return false;
            try { return api.BeforeResume(witness.DetachedCopy(), remainingMilliseconds); }
            catch { return false; }
        }
        private static readonly Encoding StrictUtf16 = new UnicodeEncoding(false, false, true);
        private static string Digest(byte[] bytes) {
            using (SHA256 hash = SHA256.Create()) { return BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant(); }
        }
        // Only the explicitly supplied map is read. Never copy the ambient environment.
        // Reject ambiguous names and bound the allocation before process creation.
        public static byte[] BuildLaunchEnvironment(IDictionary<string, string> supplied) {
            if (supplied == null || supplied.Count > 256) throw new ArgumentException("Explicit launch environment required.");
            SortedDictionary<string, string> ordered = new SortedDictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            int units = 1;
            foreach (KeyValuePair<string, string> pair in supplied) {
                if (String.IsNullOrEmpty(pair.Key) || pair.Key.Length > 256 || pair.Value == null || pair.Value.Length > 32767) throw new ArgumentException("Invalid launch environment entry.");
                for (int index = 0; index < pair.Key.Length; index++) {
                    char value = pair.Key[index];
                    if (!(value >= 'A' && value <= 'Z') && !(value >= 'a' && value <= 'z') && !(value == '_') && !(index > 0 && value >= '0' && value <= '9')) throw new ArgumentException("Invalid launch environment name.");
                }
                if (pair.Value.IndexOf('\0') >= 0 || ordered.ContainsKey(pair.Key)) throw new ArgumentException("Ambiguous launch environment entry.");
                units = checked(units + pair.Key.Length + pair.Value.Length + 2);
                if (units > 524288) throw new ArgumentException("Launch environment exceeds 1 MiB bound.");
                ordered.Add(pair.Key, pair.Value);
            }
            StringBuilder block = new StringBuilder();
            foreach (KeyValuePair<string, string> pair in ordered) { block.Append(pair.Key).Append('=').Append(pair.Value).Append('\0'); }
            if (ordered.Count == 0) block.Append('\0');
            block.Append('\0');
            return StrictUtf16.GetBytes(block.ToString());
        }

        private static int Error() { int error = Marshal.GetLastWin32Error(); return error == 0 ? -1 : error; }
        private static void Check(bool ok, string stage) { if (!ok) throw new Win32Exception(Error(), stage); }
        private static void Close(ref IntPtr handle, ValidatorProcessResult result) {
            if (handle != IntPtr.Zero) {
                if (!Native.CloseHandle(handle)) result.cleanup_error_code = Error();
                handle = IntPtr.Zero;
            }
        }
        public static ValidatorProcessResult Run(string executable, string arguments, string directory, int milliseconds, int cleanupMilliseconds, ValidatorProcessApi api) {
            return Run(executable, arguments, directory, milliseconds, cleanupMilliseconds, api, null, false, 0);
        }
        public static ValidatorProcessResult Run(string executable, string arguments, string directory, int milliseconds, int cleanupMilliseconds, ValidatorProcessApi api, string standardInput, bool utf8Streams, int maximumOutputCharacters) {
            return Run(executable, arguments, directory, milliseconds, cleanupMilliseconds, api, standardInput, utf8Streams, maximumOutputCharacters, null);
        }
        public static ValidatorProcessResult Run(string executable, string arguments, string directory, int milliseconds, int cleanupMilliseconds, ValidatorProcessApi api, string standardInput, bool utf8Streams, int maximumOutputCharacters, IDictionary<string, string> launchEnvironment) {
            return Run(executable, arguments, directory, milliseconds, cleanupMilliseconds, api, standardInput, utf8Streams, maximumOutputCharacters, launchEnvironment, false);
        }
        public static ValidatorProcessResult Run(string executable, string arguments, string directory, int milliseconds, int cleanupMilliseconds, ValidatorProcessApi api, string standardInput, bool utf8Streams, int maximumOutputCharacters, IDictionary<string, string> launchEnvironment, bool observationRequired) {
            if (observationRequired && (launchEnvironment == null || api == null)) throw new ArgumentException("Observation requires exact launch input and a runtime API.");
            if (milliseconds < 1 || cleanupMilliseconds < 100 || maximumOutputCharacters < 0) throw new ArgumentOutOfRangeException("milliseconds");
            byte[] inputBytes = null;
            if (standardInput != null) {
                Encoding inputEncoding = new UTF8Encoding(false, true);
                if (inputEncoding.GetByteCount(standardInput) > 16777216) throw new ArgumentOutOfRangeException("standardInput", "Input exceeds 16 MiB UTF8 bound.");
                inputBytes = inputEncoding.GetBytes(standardInput);
            }
            byte[] environmentBytes = launchEnvironment == null ? null : BuildLaunchEnvironment(launchEnvironment);
            string launchCommand = "\"" + executable + "\" " + arguments;
            ValidatorLaunchWitness witness = null;
            if (environmentBytes != null) {
                if (String.IsNullOrEmpty(executable) || String.IsNullOrEmpty(directory) || executable.IndexOf('\0') >= 0 || directory.IndexOf('\0') >= 0 || launchCommand.IndexOf('\0') >= 0 || launchCommand.Length > 32766) throw new ArgumentException("Invalid witnessed launch input.");
                witness = new ValidatorLaunchWitness();
                witness.application_utf16_sha256 = Digest(StrictUtf16.GetBytes(executable));
                witness.command_line_utf16_sha256 = Digest(StrictUtf16.GetBytes(launchCommand));
                witness.directory_utf16_sha256 = Digest(StrictUtf16.GetBytes(directory));
                witness.environment_block_utf16_sha256 = Digest(environmentBytes);
                witness.environment_block_bytes = environmentBytes.Length;
                witness.stdin_present = inputBytes != null;
                witness.stdin_utf8_sha256 = Digest(inputBytes ?? new byte[0]);
            }
            Encoding outputEncoding = utf8Streams ? new UTF8Encoding(false, false) : Console.OutputEncoding;
            if (api == null) api = new ValidatorProcessApi();
            ValidatorProcessResult result = new ValidatorProcessResult();
            result.launch_witness = witness;
            result.observation_required = observationRequired;
            IntPtr job = IntPtr.Zero, outputRead = IntPtr.Zero, outputWrite = IntPtr.Zero;
            IntPtr errorRead = IntPtr.Zero, errorWrite = IntPtr.Zero, inputRead = IntPtr.Zero, inputWrite = IntPtr.Zero;
            IntPtr attributes = IntPtr.Zero, handleList = IntPtr.Zero, environmentBlock = IntPtr.Zero;
            bool attributesInitialized = false, assigned = false, launched = false, completed = false, cancellationOk = true;
            Native.ProcessInfo child = new Native.ProcessInfo();
            PipeDrain stdout = null, stderr = null;
            PipeInput stdin = null;
            Stopwatch watch = Stopwatch.StartNew();
            try {
                job = Native.CreateJobObjectW(IntPtr.Zero, null);
                Check(job != IntPtr.Zero, "Create private job");
                Native.ExtendedLimits limits = new Native.ExtendedLimits();
                limits.Basic.Flags = 0x2000; // KILL_ON_JOB_CLOSE; no breakaway permission.
                Check(Native.SetInformationJobObject(job, 9, ref limits, (uint)Marshal.SizeOf(typeof(Native.ExtendedLimits))), "Set private job limits");
                Native.Security security = new Native.Security(); security.Length = Marshal.SizeOf(typeof(Native.Security)); security.Inherit = 1;
                Check(Native.CreatePipe(out outputRead, out outputWrite, ref security, 0), "Create stdout pipe");
                Check(Native.CreatePipe(out errorRead, out errorWrite, ref security, 0), "Create stderr pipe");
                Check(Native.CreatePipe(out inputRead, out inputWrite, ref security, 0), "Create stdin pipe");
                Check(Native.SetHandleInformation(outputRead, 1, 0), "Protect stdout reader");
                Check(Native.SetHandleInformation(errorRead, 1, 0), "Protect stderr reader");
                Check(Native.SetHandleInformation(inputWrite, 1, 0), "Protect stdin writer");
                Native.StartupEx startup = new Native.StartupEx(); startup.Info.Size = Marshal.SizeOf(typeof(Native.StartupEx));
                startup.Info.Flags = 0x100; startup.Info.Input = inputRead; startup.Info.Output = outputWrite; startup.Info.Error = errorWrite;
                IntPtr size = IntPtr.Zero;
                Native.InitializeProcThreadAttributeList(IntPtr.Zero, 1, 0, ref size);
                attributes = Marshal.AllocHGlobal(size);
                Check(Native.InitializeProcThreadAttributeList(attributes, 1, 0, ref size), "Initialize inherited handle list");
                attributesInitialized = true;
                handleList = Marshal.AllocHGlobal(3 * IntPtr.Size);
                Marshal.WriteIntPtr(handleList, 0, inputRead); Marshal.WriteIntPtr(handleList, IntPtr.Size, outputWrite); Marshal.WriteIntPtr(handleList, 2 * IntPtr.Size, errorWrite);
                Check(Native.UpdateProcThreadAttribute(attributes, 0, new IntPtr(0x20002), handleList, new IntPtr(3 * IntPtr.Size), IntPtr.Zero, IntPtr.Zero), "Restrict inherited handles");
                startup.Attributes = attributes;
                // The private job owns the child before any target instruction can run.
                uint creationFlags = 0x08080004;
                if (environmentBytes != null) {
                    environmentBlock = Marshal.AllocHGlobal(environmentBytes.Length);
                    Marshal.Copy(environmentBytes, 0, environmentBlock, environmentBytes.Length);
                    creationFlags |= 0x00000400; // CREATE_UNICODE_ENVIRONMENT
                }
                Check(Native.CreateProcessW(executable, new StringBuilder(launchCommand), IntPtr.Zero, IntPtr.Zero, true, creationFlags, environmentBlock, directory, ref startup, out child), "Create suspended validator");
                if (witness != null) { witness.created = true; witness.child_process_id = child.ProcessId; witness.creator_process_id = Native.GetCurrentProcessId(); }
                result.root_process_id = child.ProcessId;
                Close(ref outputWrite, result); Close(ref errorWrite, result); Close(ref inputRead, result);
                if (inputBytes == null) Close(ref inputWrite, result);
                Check(api.Assign(job, child.Process), "Assign suspended validator to private job"); assigned = true;
                if (witness != null) {
                    witness.assigned_before_resume = true;
                    long created, exited, kernel, user;
                    Check(Native.GetProcessTimes(child.Process, out created, out exited, out kernel, out user), "Read owned child creation time");
                    StringBuilder image = new StringBuilder(32768); uint imageSize = 32768;
                    Check(Native.QueryFullProcessImageNameW(child.Process, 0, image, ref imageSize), "Read owned child image path");
                    Check(created > 0 && imageSize > 0 && imageSize < 32768 && witness.creator_process_id > 0 && witness.child_process_id > 0, "Validate owned child identity");
                    Check(String.Equals(image.ToString(), executable, StringComparison.OrdinalIgnoreCase), "Owned child image differs from selected executable");
                    witness.child_creation_filetime = created; witness.actual_image_path = image.ToString();
                }
                stdout = new PipeDrain(outputRead, outputEncoding, maximumOutputCharacters); stderr = new PipeDrain(errorRead, outputEncoding, maximumOutputCharacters);
                stdout.Start(Math.Max(1, milliseconds - (int)Math.Min(watch.ElapsedMilliseconds, milliseconds - 1)));
                stderr.Start(Math.Max(1, milliseconds - (int)Math.Min(watch.ElapsedMilliseconds, milliseconds - 1)));
                if (inputBytes != null) {
                    stdin = new PipeInput(inputWrite, inputBytes); inputWrite = IntPtr.Zero;
                    stdin.Start(Math.Max(1, milliseconds - (int)Math.Min(watch.ElapsedMilliseconds, milliseconds - 1)));
                }
                if (watch.ElapsedMilliseconds >= milliseconds) { result.timed_out = true; }
                else {
                    if (observationRequired) {
                        int remaining = (int)Math.Max(0, milliseconds - watch.ElapsedMilliseconds);
                        result.observation_ready = CheckObservationReady(api, witness, remaining);
                        Check(result.observation_ready && watch.ElapsedMilliseconds < milliseconds, "Pre-resume observation unavailable or expired");
                    }
                    Check(api.Resume(child.Thread) != UInt32.MaxValue, "Resume contained validator"); launched = true;
                    if (witness != null) witness.resumed = true;
                    while (watch.ElapsedMilliseconds < milliseconds) {
                        uint active;
                        Check(api.Accounting(job, out active), "Query owned job completion");
                        uint wait = api.Wait(child.Process);
                        Check(wait != UInt32.MaxValue, "Wait for owned validator");
                        if (wait == 0 && active == 0 && stdout.Done && stderr.Done && (stdin == null || stdin.Done)) { completed = true; break; }
                        if (stdin != null && stdin.Done && stdin.Error != 0) { result.process_error = "Owned stdin write failed."; break; }
                        Thread.Sleep(5);
                    }
                    if (!completed && result.process_error.Length == 0) result.timed_out = true;
                }
            }
            catch (Exception error) {
                result.startup_failed = !launched;
                result.process_error = error.Message;
            }
            finally {
                Stopwatch cleanup = Stopwatch.StartNew();
                if (child.Process == IntPtr.Zero) { result.root_exit_confirmed = true; result.tree_exit_confirmed = true; }
                else {
                    if (!completed) {
                        try {
                            // An unassigned root is still suspended and cannot have descendants.
                            cancellationOk = assigned ? api.Cancel(job) : Native.TerminateProcess(child.Process, 124);
                            if (!cancellationOk) result.cancellation_error_code = Error();
                        }
                        catch { cancellationOk = false; result.cancellation_error_code = -1; }
                    }
                    while (cleanup.ElapsedMilliseconds < cleanupMilliseconds - 100) {
                        try {
                            uint wait = api.Wait(child.Process);
                            if (wait == UInt32.MaxValue) result.cleanup_error_code = Error();
                            result.root_exit_confirmed = wait == 0;
                            uint active = 0;
                            bool accounted = !assigned || api.Accounting(job, out active);
                            if (!accounted) result.cleanup_error_code = Error();
                            result.tree_exit_confirmed = assigned ? (accounted && active == 0) : result.root_exit_confirmed;
                        }
                        catch { result.cleanup_error_code = -1; }
                        if (result.root_exit_confirmed && result.tree_exit_confirmed && (stdout == null || stdout.Done) && (stderr == null || stderr.Done) && (stdin == null || stdin.Done)) break;
                        Thread.Sleep(5);
                    }
                    uint code;
                    if (result.root_exit_confirmed && Native.GetExitCodeProcess(child.Process, out code)) result.exit_code = unchecked((int)code);
                }
                // Cancel any still-blocked owned readers; never wait without a remaining bound.
                if (stdin != null && !stdin.Done) stdin.Cancel();
                if (stdout != null && !stdout.Done) stdout.Cancel();
                if (stderr != null && !stderr.Done) stderr.Cancel();
                bool inputJoined = stdin == null || stdin.Join((int)Math.Max(0, cleanupMilliseconds - cleanup.ElapsedMilliseconds));
                result.stdin_writer_joined = inputJoined;
                result.stdin_bytes_written = stdin == null ? 0 : stdin.Written;
                result.stdin_error_code = stdin == null ? 0 : stdin.Error;
                result.stdin_completed = inputBytes == null || (stdin != null && inputJoined && stdin.Error == 0 && stdin.CloseError == 0 && stdin.Written == inputBytes.Length);
                bool outputJoined = stdout == null || stdout.Join((int)Math.Max(0, cleanupMilliseconds - cleanup.ElapsedMilliseconds));
                bool errorJoined = stderr == null || stderr.Join((int)Math.Max(0, cleanupMilliseconds - cleanup.ElapsedMilliseconds));
                result.drains_completed = outputJoined && errorJoined && (stdout == null || stdout.Error == 0) && (stderr == null || stderr.Error == 0);
                if (stdout != null) { result.stdout = stdout.Text; result.stdout_truncated = stdout.Truncated; }
                if (stderr != null) { result.stderr = stderr.Text; result.stderr_truncated = stderr.Truncated; }
                if ((!result.drains_completed || !inputJoined) && result.cleanup_error_code == 0) result.cleanup_error_code = -1;
                // Closing a job is a final safety action, never proof that cancellation completed.
                Close(ref child.Thread, result); Close(ref child.Process, result); Close(ref job, result);
                Close(ref outputWrite, result); Close(ref errorWrite, result); Close(ref inputRead, result); Close(ref inputWrite, result);
                Close(ref outputRead, result); Close(ref errorRead, result);
                if (stdin != null && inputJoined) stdin.Dispose();
                result.stdin_close_error_code = stdin == null ? 0 : stdin.CloseError;
                if (result.stdin_close_error_code != 0) { result.cleanup_error_code = result.stdin_close_error_code; result.stdin_completed = false; }
                if (stdout != null && outputJoined) stdout.Dispose();
                if (stderr != null && errorJoined) stderr.Dispose();
                if (attributesInitialized) Native.DeleteProcThreadAttributeList(attributes);
                if (attributes != IntPtr.Zero) Marshal.FreeHGlobal(attributes);
                if (handleList != IntPtr.Zero) Marshal.FreeHGlobal(handleList);
                if (environmentBlock != IntPtr.Zero) {
                    for (int offset = 0; offset < environmentBytes.Length; offset++) Marshal.WriteByte(environmentBlock, offset, 0);
                    Marshal.FreeHGlobal(environmentBlock);
                }
                if (environmentBytes != null) Array.Clear(environmentBytes, 0, environmentBytes.Length);
                bool confirmed = cancellationOk && result.root_exit_confirmed && result.tree_exit_confirmed && result.drains_completed && inputJoined;
                // Setup errors may be fully reaped, but cancellation/wait/stream uncertainty never permits retry.
                result.cleanup_state = confirmed && result.cleanup_error_code == 0 ? "CONFIRMED" : "UNRESOLVED";
                result.retry_allowed = result.cleanup_state == "CONFIRMED" && (!observationRequired || result.observation_ready);
                if (result.timed_out) result.stderr += " Validator timed out within its original execution deadline.";
            }
            return result;
        }
    }
}
'@
}

function Invoke-AiOsValidatorProcess {
    param(
        [string]$PowerShellExe,
        [string[]]$Arguments,
        [ValidateRange(1, 2147483)][int]$TimeoutSeconds = 60,
        [ValidateRange(100, 60000)][int]$CleanupMilliseconds = 2000,
        [object]$ProcessApi = $null,
        [AllowNull()][string]$StandardInput = $null,
        [AllowNull()][string]$WorkingDirectory = $null,
        [AllowNull()][string]$RawArguments = $null,
        [switch]$Utf8Streams,
        [ValidateRange(0, 16777216)][int]$MaximumOutputCharacters = 0,
        [AllowNull()][System.Collections.IDictionary]$LaunchEnvironment = $null,
        [switch]$RequireObservation
    )

    if ((Get-Variable -Name AiOsValidatorCleanupUnresolved -Scope Script -ErrorAction SilentlyContinue) -and $script:AiOsValidatorCleanupUnresolved) {
        return [pscustomobject]@{ timed_out = $false; startup_failed = $true; exit_code = $null; stdout = ""; stderr = "Earlier owned cleanup is unresolved."; process_error = "Earlier owned cleanup is unresolved."; cleanup_state = "UNRESOLVED"; root_exit_confirmed = $false; tree_exit_confirmed = $false; drains_completed = $false; cleanup_error_code = -1; cancellation_error_code = 0; retry_allowed = $false }
    }
    try {
        Initialize-AiOsOwnedValidatorProcess
    }
    catch {
        # Compilation/setup never falls back to an uncontained launch.
        $run = [pscustomobject]@{ timed_out = $false; startup_failed = $true; exit_code = $null; stdout = ""; stderr = "Owned validator setup failed."; process_error = $_.Exception.Message; cleanup_state = "CONFIRMED"; root_exit_confirmed = $true; tree_exit_confirmed = $true; drains_completed = $true; cleanup_error_code = 0; cancellation_error_code = 0; retry_allowed = $false }
        return $run
    }
    try {
        $directory = if ([string]::IsNullOrWhiteSpace($WorkingDirectory)) { (Get-Location).ProviderPath } else { $WorkingDirectory }
        $inputValue = if ($PSBoundParameters.ContainsKey('StandardInput') -and $null -ne $StandardInput) { $StandardInput } else { $null }
        $joinedArguments = if ($PSBoundParameters.ContainsKey('RawArguments')) { $RawArguments } else { Join-AiOsProcessArguments -Arguments $Arguments }
        if ($PSBoundParameters.ContainsKey('LaunchEnvironment')) {
            if ($null -eq $LaunchEnvironment) { throw 'Explicit launch environment cannot be null.' }
            $signature = @([string], [string], [string], [int], [int], [AiOs.ValidatorProcessApi], [string], [bool], [int], [Collections.Generic.IDictionary[string,string]])
            if ($null -eq [AiOs.ValidatorProcess].GetMethod('Run', $signature)) { throw 'Loaded launch primitive lacks explicit environment support.' }
            $exact = [Collections.Generic.Dictionary[string,string]]::new([StringComparer]::OrdinalIgnoreCase)
            foreach ($entry in $LaunchEnvironment.GetEnumerator()) {
                if ($entry.Key -isnot [string] -or $entry.Value -isnot [string]) { throw 'Launch environment entries must be strings.' }
                $exact.Add($entry.Key, $entry.Value)
            }
            if($RequireObservation){
                $observedSignature = $signature + @([bool])
                if($null -eq [AiOs.ValidatorProcess].GetMethod('Run',$observedSignature) -or $ProcessApi -isnot [AiOs.ValidatorProcessApi]){throw 'Loaded primitive lacks the runtime observation port.'}
                $run = [AiOs.ValidatorProcess]::Run($PowerShellExe, $joinedArguments, $directory, ($TimeoutSeconds * 1000), $CleanupMilliseconds, $ProcessApi, $inputValue, [bool]$Utf8Streams, $MaximumOutputCharacters, $exact, $true)
            }else{
            $run = [AiOs.ValidatorProcess]::Run($PowerShellExe, $joinedArguments, $directory, ($TimeoutSeconds * 1000), $CleanupMilliseconds, $ProcessApi, $inputValue, [bool]$Utf8Streams, $MaximumOutputCharacters, $exact)
            }
        } else {
        if($RequireObservation){throw 'Observation requires an explicit launch environment.'}
        $run = [AiOs.ValidatorProcess]::Run($PowerShellExe, $joinedArguments, $directory, ($TimeoutSeconds * 1000), $CleanupMilliseconds, $ProcessApi, $inputValue, [bool]$Utf8Streams, $MaximumOutputCharacters)
        }
    }
    catch {
        # A host failure after native entry cannot establish whether cleanup finished.
        $run = [pscustomobject]@{ timed_out = $false; startup_failed = $true; exit_code = $null; stdout = ""; stderr = "Owned validator cleanup could not be confirmed."; process_error = $_.Exception.Message; cleanup_state = "UNRESOLVED"; root_exit_confirmed = $false; tree_exit_confirmed = $false; drains_completed = $false; cleanup_error_code = -1; cancellation_error_code = 0; retry_allowed = $false }
    }
    if ($run.cleanup_state -eq "UNRESOLVED") { $script:AiOsValidatorCleanupUnresolved = $true }
    return $run
}

$repoRoot = Get-AiOsRepoRoot
Set-Location -LiteralPath $repoRoot
$generatedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$resolvedConfigPath = if ([System.IO.Path]::IsPathRooted($ConfigPath)) { $ConfigPath } else { Join-Path $repoRoot $ConfigPath }

try {
    $config = Get-Content -LiteralPath $resolvedConfigPath -Raw | ConvertFrom-Json
}
catch {
    Write-Error "Unable to read validator chain config: $($_.Exception.Message)"
    exit 1
}

$chainId = [string](Get-AiOsPropertyValue -InputObject $config -Names @("chain_id", "validator_chain_id") -DefaultValue "UNKNOWN_VALIDATOR_CHAIN")
$results = [System.Collections.Generic.List[object]]::new()
$chainResult = "PASS"
$validatorsRun = 0
$validatorsPassed = 0
$validatorsFailed = 0
$validatorsMissing = 0
$validatorsTimedOut = 0
$powershellExe = (Get-Command powershell -ErrorAction Stop).Source
$orderedValidators = @($config.validators | Sort-Object { [int](Get-AiOsPropertyValue -InputObject $_ -Names @("order") -DefaultValue 0) })

foreach ($validator in $orderedValidators) {
    $validatorId = [string](Get-AiOsPropertyValue -InputObject $validator -Names @("validator_id", "name", "check_id") -DefaultValue "UNKNOWN_VALIDATOR")
    $scriptPath = [string](Get-AiOsPropertyValue -InputObject $validator -Names @("script_path", "path") -DefaultValue "")
    if ([string]::IsNullOrWhiteSpace($scriptPath)) {
        $scriptPath = Get-AiOsScriptForValidator -ValidatorId $validatorId
    }

    $scriptPath = ConvertTo-AiOsRelativePath -Path $scriptPath
    $required = [bool](Get-AiOsPropertyValue -InputObject $validator -Names @("required") -DefaultValue $false)
    $severity = [string](Get-AiOsPropertyValue -InputObject $validator -Names @("severity_on_failure", "severity") -DefaultValue "FAIL")
    $stopOnFailRaw = Get-AiOsPropertyValue -InputObject $validator -Names @("stop_on_fail") -DefaultValue $null
    $stopOnFail = if ($null -ne $stopOnFailRaw) { [bool]$stopOnFailRaw } else { ($severity -eq "FAIL") }
    $resolvedScriptPath = if ([string]::IsNullOrWhiteSpace($scriptPath)) { "" } elseif ([System.IO.Path]::IsPathRooted($scriptPath)) { $scriptPath } else { Join-Path $repoRoot $scriptPath }

    if ([string]::IsNullOrWhiteSpace($scriptPath) -or -not (Test-Path -LiteralPath $resolvedScriptPath -PathType Leaf)) {
        $validatorsMissing++
        if ($required) { $validatorsFailed++ }
        $result = "MISSING"
        $results.Add([pscustomobject]@{
            validator_id = $validatorId
            script_path = $scriptPath
            result = $result
            exit_code = $null
            required = $required
            stop_on_fail = $stopOnFail
            output_preview = "Validator script missing."
        }) | Out-Null

        if ($required -and $stopOnFail) {
            $chainResult = "BLOCKED"
            break
        }
        elseif ($required -and $chainResult -ne "BLOCKED") {
            $chainResult = "FAIL"
        }

        continue
    }

    $validatorsRun++
    $args = Get-AiOsValidatorArguments -ValidatorId $validatorId -ScriptPath $resolvedScriptPath -ConfigPath $ConfigPath
    $run = Invoke-AiOsValidatorProcess -PowerShellExe $powershellExe -Arguments $args -TimeoutSeconds 60

    if ($run.timed_out) {
        $validatorsTimedOut++
        if ($required) { $validatorsFailed++ }
        $result = "TIMEOUT"
        $exitCode = $null
        $preview = ConvertTo-AiOsPreview -Text $run.stderr
    }
    elseif ($run.exit_code -eq 0) {
        $validatorsPassed++
        $result = "PASS"
        $exitCode = $run.exit_code
        $preview = ConvertTo-AiOsPreview -Text $run.stdout
    }
    else {
        if ($required) { $validatorsFailed++ }
        $result = "FAIL"
        $exitCode = $run.exit_code
        $previewText = if (-not [string]::IsNullOrWhiteSpace($run.stderr)) { $run.stderr } else { $run.stdout }
        $preview = ConvertTo-AiOsPreview -Text $previewText
    }

    $results.Add([pscustomobject]@{
        validator_id = $validatorId
        script_path = $scriptPath
        result = $result
        exit_code = $exitCode
        required = $required
        stop_on_fail = $stopOnFail
        output_preview = $preview
    }) | Out-Null

    if ($result -ne "PASS" -and $required -and $stopOnFail) {
        $chainResult = "BLOCKED"
        break
    }
    elseif ($result -ne "PASS" -and $required -and $chainResult -ne "BLOCKED") {
        $chainResult = "FAIL"
    }
}

$receipt = [pscustomobject]@{
    schema = "AIOS_VALIDATOR_CHAIN_RECEIPT.v1"
    chain_id = $chainId
    generated_at = $generatedAt
    chain_result = $chainResult
    validators_run = $validatorsRun
    validators_passed = $validatorsPassed
    validators_failed = $validatorsFailed
    validators_missing = $validatorsMissing
    validators_timeout = $validatorsTimedOut
    results = @($results)
}

$receipt | ConvertTo-Json -Depth 12
exit 0
