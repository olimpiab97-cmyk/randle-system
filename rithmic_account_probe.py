import os
import subprocess
import sys
import tempfile
import textwrap
import zipfile
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
RITHMIC_ZIP_PATH = BASE_DIR / "Rithmic API" / "RApiPlus.NET.13.7.0.0.zip"
RITHMIC_CACHE_DIR = Path(tempfile.gettempdir()) / "rithmic_account_probe"
RITHMIC_RUNTIME_DIR = RITHMIC_CACHE_DIR / "runtime"
RAPIPLUS_DLL_PATH = RITHMIC_RUNTIME_DIR / "rapiplus.dll"
PROBE_BRIDGE_PATH = RITHMIC_CACHE_DIR / "rithmic_account_probe.ps1"
ENGINE_CREATION_TIMEOUT_SECONDS = 20

# Credentials are read only from environment variables and must never be printed.
RITHMIC_USER = os.getenv("RITHMIC_USER", "").strip()
RITHMIC_PASSWORD = os.getenv("RITHMIC_PASSWORD", "").strip()
RITHMIC_MD_CONNECTION_POINT = os.getenv("RITHMIC_MD_CONNECTION_POINT", "login_agent_tp_paper_sumc").strip() or "login_agent_tp_paper_sumc"
RITHMIC_TS_CONNECTION_POINT = os.getenv("RITHMIC_TS_CONNECTION_POINT", "login_agent_op_paperc").strip() or "login_agent_op_paperc"
RITHMIC_PNL_CONNECTION_POINT = os.getenv("RITHMIC_PNL_CONNECTION_POINT", "").strip()
RITHMIC_REPOSITORY_CONNECTION_POINT = os.getenv("RITHMIC_REPOSITORY_CONNECTION_POINT", "login_agent_repositoryc").strip() or "login_agent_repositoryc"
DISCOVERED_PNL_CONNECTION_CANDIDATES = (
    "login_agent_pnlc (generic Rithmic Test/UAT sample; not confirmed for AMP paper)",
)


def ensure_runtime_files():
    if not RITHMIC_ZIP_PATH.exists():
        raise FileNotFoundError(f"Missing Rithmic API zip: {RITHMIC_ZIP_PATH}")

    RITHMIC_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    if not RAPIPLUS_DLL_PATH.exists():
        with zipfile.ZipFile(RITHMIC_ZIP_PATH) as archive:
            runtime_prefix = "13.7.0.0/win10/lib_472/"
            for member in archive.infolist():
                if not member.filename.startswith(runtime_prefix) or member.is_dir():
                    continue

                relative_path = member.filename[len(runtime_prefix):]
                target_path = RITHMIC_RUNTIME_DIR / relative_path
                target_path.parent.mkdir(parents=True, exist_ok=True)

                with archive.open(member) as src, target_path.open("wb") as dst:
                    dst.write(src.read())

    return RAPIPLUS_DLL_PATH


def validate_env():
    missing = []
    if not RITHMIC_USER:
        missing.append("RITHMIC_USER")
    if not RITHMIC_PASSWORD:
        missing.append("RITHMIC_PASSWORD")
    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))


def build_probe_bridge():
    return textwrap.dedent(
        r"""
        param(
            [string]$DllPath,
            [string]$UserName,
            [string]$Password,
            [string]$MdConnectionPoint,
            [string]$TsConnectionPoint,
            [string]$PnlConnectionPoint,
            [string]$DiscoveredPnlCandidates,
            [string]$RepositoryConnectionPoint
        )

        $ErrorActionPreference = "Stop"

        Add-Type -Path $DllPath

        Add-Type -ReferencedAssemblies @($DllPath) -TypeDefinition @"
        using System;
        using System.Collections;
        using System.Collections.Generic;
        using System.Collections.ObjectModel;
        using System.Globalization;
        using System.Linq;
        using System.Reflection;
        using System.Text;
        using System.Threading;
        using System.Threading.Tasks;
        using com.omnesys.omne.om;
        using com.omnesys.rapi;

        public enum ProbeLoginStatus
        {
            NotLoggedIn,
            LoginInProgress,
            LoginFailed,
            LoggedIn
        }

        public class AccountProbeAdmCallbacks : AdmCallbacks
        {
            public override void Alert(AlertInfo info)
            {
                var sb = new StringBuilder();
                info.Dump(sb);
                Console.WriteLine("ADM|" + sb.ToString().Replace("\r", " ").Replace("\n", " "));
            }
        }

        public class AccountProbeCallbacks : RCallbacks
        {
            public ProbeLoginStatus RepositoryLoginStatus = ProbeLoginStatus.NotLoggedIn;
            public bool LoggedIntoMd = false;
            public bool LoggedIntoTs = false;
            public bool LoggedIntoPnl = false;
            public bool ShutdownRequested = false;
            public bool ReceivedPnlInfo = false;
            public List<AccountInfo> Accounts = new List<AccountInfo>();

            private static readonly string[] CandidateTerms = new string[]
            {
                "account",
                "balance",
                "cash",
                "equity",
                "net",
                "liq",
                "liquidation",
                "buying",
                "power",
                "margin",
                "pnl",
                "profit",
                "loss",
                "realized",
                "unrealized",
                "rms"
            };

            private static bool IsCandidateName(string value)
            {
                if (String.IsNullOrWhiteSpace(value))
                {
                    return false;
                }

                string lower = value.ToLowerInvariant();
                foreach (string term in CandidateTerms)
                {
                    if (lower.Contains(term))
                    {
                        return true;
                    }
                }
                return false;
            }

            private static string FormatScalar(object value)
            {
                if (value == null)
                {
                    return "<null>";
                }
                if (value is string)
                {
                    return value.ToString();
                }
                if (value is DateTime)
                {
                    return ((DateTime)value).ToString("o", CultureInfo.InvariantCulture);
                }
                if (value.GetType().IsPrimitive || value is decimal)
                {
                    return Convert.ToString(value, CultureInfo.InvariantCulture);
                }
                return value.ToString();
            }

            private static void EmitFields(string prefix, object info, int depth)
            {
                if (info == null)
                {
                    Console.WriteLine(prefix + "|<null>");
                    return;
                }
                if (depth > 2)
                {
                    Console.WriteLine(prefix + "|<max_depth>|" + info.GetType().FullName);
                    return;
                }

                Type type = info.GetType();
                Console.WriteLine(prefix + "|OBJECT_TYPE|" + type.FullName);
                foreach (PropertyInfo property in type.GetProperties(BindingFlags.Public | BindingFlags.Instance).OrderBy(p => p.Name))
                {
                    if (!property.CanRead || property.GetIndexParameters().Length > 0)
                    {
                        continue;
                    }

                    object value = null;
                    try
                    {
                        value = property.GetValue(info, null);
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine(prefix + "|FIELD|" + property.Name + "|<error:" + ex.GetType().Name + ">");
                        continue;
                    }

                    if (value == null || value is string || value is DateTime || value.GetType().IsPrimitive || value is decimal)
                    {
                        Console.WriteLine(prefix + "|FIELD|" + property.Name + "|" + FormatScalar(value));
                        continue;
                    }

                    IEnumerable enumerable = value as IEnumerable;
                    if (enumerable != null)
                    {
                        int index = 0;
                        foreach (object item in enumerable)
                        {
                            if (index >= 5)
                            {
                                Console.WriteLine(prefix + "|FIELD|" + property.Name + "|...");
                                break;
                            }
                            if (item == null || item is string || item.GetType().IsPrimitive || item is decimal)
                            {
                                Console.WriteLine(prefix + "|FIELD|" + property.Name + "[" + index + "]|" + FormatScalar(item));
                            }
                            else
                            {
                                EmitFields(prefix + "|FIELD|" + property.Name + "[" + index + "]", item, depth + 1);
                            }
                            index++;
                        }
                        if (index == 0)
                        {
                            Console.WriteLine(prefix + "|FIELD|" + property.Name + "|<empty>");
                        }
                        continue;
                    }

                    EmitFields(prefix + "|FIELD|" + property.Name, value, depth + 1);
                }
            }

            public static void PrintCandidateApiSurface()
            {
                Console.WriteLine("PROBE|candidate_rithmic_callbacks_begin");
                foreach (MethodInfo method in typeof(RCallbacks).GetMethods(BindingFlags.Public | BindingFlags.Instance).OrderBy(m => m.Name))
                {
                    string signature = method.Name + "(" + String.Join(",", method.GetParameters().Select(p => p.ParameterType.Name + " " + p.Name).ToArray()) + ")";
                    if (IsCandidateName(signature))
                    {
                        Console.WriteLine("CALLBACK_CANDIDATE|" + signature);
                    }
                }
                Console.WriteLine("PROBE|candidate_rithmic_callbacks_end");

                Console.WriteLine("PROBE|candidate_engine_methods_begin");
                foreach (MethodInfo method in typeof(REngine).GetMethods(BindingFlags.Public | BindingFlags.Instance).OrderBy(m => m.Name))
                {
                    string signature = method.Name + "(" + String.Join(",", method.GetParameters().Select(p => p.ParameterType.Name + " " + p.Name).ToArray()) + ")";
                    if (IsCandidateName(signature))
                    {
                        Console.WriteLine("ENGINE_METHOD_CANDIDATE|" + signature);
                    }
                }
                Console.WriteLine("PROBE|candidate_engine_methods_end");
            }

            public void RequestShutdown()
            {
                ShutdownRequested = true;
            }

            public override void Alert(AlertInfo info)
            {
                var sb = new StringBuilder();
                info.Dump(sb);
                string alertText = sb.ToString().Replace("\r", " ").Replace("\n", " ");
                Console.WriteLine("ALERT|" + alertText);
                string connectionName = info.ConnectionId.ToString();

                if (info.ConnectionId == ConnectionId.Repository)
                {
                    if (info.AlertType == AlertType.LoginComplete)
                    {
                        RepositoryLoginStatus = ProbeLoginStatus.LoggedIn;
                        Console.WriteLine("STATUS|repository_login_complete");
                    }
                    else if (info.AlertType == AlertType.LoginFailed)
                    {
                        RepositoryLoginStatus = ProbeLoginStatus.LoginFailed;
                        Console.WriteLine("STATUS|repository_login_failed");
                    }
                }

                if (info.ConnectionId == ConnectionId.MarketData && info.AlertType == AlertType.LoginComplete)
                {
                    LoggedIntoMd = true;
                    Console.WriteLine("STATUS|market_data_login_complete");
                }

                if (info.ConnectionId == ConnectionId.TradingSystem && info.AlertType == AlertType.LoginComplete)
                {
                    LoggedIntoTs = true;
                    Console.WriteLine("STATUS|trading_system_login_complete");
                }

                if (info.AlertType == AlertType.LoginComplete &&
                    (connectionName.IndexOf("pnl", StringComparison.OrdinalIgnoreCase) >= 0 ||
                     alertText.IndexOf("pnl", StringComparison.OrdinalIgnoreCase) >= 0))
                {
                    LoggedIntoPnl = true;
                    Console.WriteLine("STATUS|pnl_login_complete");
                }
            }

            public override void AgreementList(AgreementListInfo info)
            {
                Console.WriteLine("STATUS|agreement_list_received");
            }

            public override void AccountList(AccountListInfo info)
            {
                Console.WriteLine("ACCOUNT_LIST|received");
                EmitFields("ACCOUNT_LIST", info, 0);
                if (info.Accounts == null)
                {
                    return;
                }

                Accounts.Clear();
                foreach (AccountInfo account in info.Accounts)
                {
                    Accounts.Add(account);
                    EmitFields("ACCOUNT", account, 0);
                }
            }

            public override void ProductRmsList(ProductRmsListInfo info)
            {
                Console.WriteLine("PRODUCT_RMS_LIST|received");
                EmitFields("PRODUCT_RMS_LIST", info, 0);
            }

            public override void PnlUpdate(PnlInfo oInfo)
            {
                ReceivedPnlInfo = true;
                Console.WriteLine("PNL_UPDATE|received");
                EmitFields("PNL_UPDATE", oInfo, 0);
            }
        }

        public static class AccountProbeRunner
        {
            public static int Run(
                string userName,
                string password,
                string mdConnectionPoint,
                string tsConnectionPoint,
                string pnlConnectionPoint,
                string discoveredPnlCandidates,
                string repositoryConnectionPoint)
            {
                AccountProbeCallbacks callbacks = new AccountProbeCallbacks();
                REngineParams engineParams = new REngineParams();
                REngine engine = null;
                Console.WriteLine("PROBE|read_only_account_probe_start");
                AccountProbeCallbacks.PrintCandidateApiSurface();
                Console.WriteLine("PROBE|connection_points|md=" + mdConnectionPoint + "|ts=" + tsConnectionPoint + "|pnl=" + pnlConnectionPoint + "|ih=<blank>");
                Console.WriteLine("PROBE|discovered_pnl_connection_candidates|" + discoveredPnlCandidates);
                if (String.IsNullOrWhiteSpace(pnlConnectionPoint))
                {
                    Console.WriteLine(
                        "ERROR|pnl_connection_point_not_configured|" +
                        "Set RITHMIC_PNL_CONNECTION_POINT after confirming the AMP/Rithmic paper PnL connection point. " +
                        "The probe will not guess by reusing the trading-system connection because that produced PnL Connection Broken."
                    );
                    return 6;
                }

                engineParams.AppName = "RithmicAccountReadOnlyProbe";
                engineParams.AppVersion = "1.0.0.0";
                engineParams.AdmCallbacks = new AccountProbeAdmCallbacks();
                engineParams.DmnSrvrAddr = "ritpz01004.01.rithmic.com:65000~ritpz04063.04.rithmic.com:65000~ritpz01004.01.rithmic.net:65000~ritpz04063.04.rithmic.net:65000~ritpz01004.01.theomne.net:65000~ritpz04063.04.theomne.net:65000~ritpz01004.01.theomne.com:65000~ritpz04063.04.theomne.com:65000";
                engineParams.DomainName = "rithmic_paper_prod_domain";
                engineParams.LicSrvrAddr = "ritpz04063.04.rithmic.com:56000~ritpz01004.01.rithmic.com:56000~ritpz04063.04.rithmic.net:56000~ritpz04063.04.theomne.net:56000~ritpz04063.04.theomne.com:56000~ritpz01000.01.rithmic.com:56000~ritpz01001.01.rithmic.com:56000~ritpz01000.01.rithmic.net:56000~ritpz01001.01.rithmic.net:56000~ritpz01000.01.theomne.net:56000~ritpz01001.01.theomne.net:56000~ritpz01000.01.theomne.com:56000~ritpz01001.01.theomne.com:56000~ritpz24050.rithmic.com:56000~ritpz24050.rithmic.net:56000~ritpz24050.theomne.net:56000~ritpz24050.theomne.com:56000~ritpz23010.rithmic.com:56000~ritpz23010.rithmic.net:56000~ritpz23010.theomne.net:56000~ritpz23010.theomne.com:56000~ritpz23011.rithmic.com:56000~ritpz23011.rithmic.net:56000~ritpz23011.theomne.net:56000~ritpz23011.theomne.com:56000~ritpz24013.rithmic.com:56000~ritpz24013.rithmic.net:56000~ritpz24013.theomne.net:56000~ritpz24013.theomne.com:56000";
                engineParams.LocBrokAddr = "ritpz04063.04.rithmic.com:64100";
                engineParams.LoggerAddr = "ritpz04063.04.rithmic.com:45454~ritpz01004.01.rithmic.com:45454~ritpz04063.04.rithmic.net:45454~ritpz01004.01.rithmic.net:45454~ritpz04063.04.theomne.net:45454~ritpz01004.01.theomne.net:45454~ritpz04063.04.theomne.com:45454~ritpz01004.01.theomne.com:45454";
                engineParams.LogFilePath = "rithmic_account_probe.log";

                try
                {
                    Console.CancelKeyPress += (sender, args) =>
                    {
                        args.Cancel = true;
                        callbacks.RequestShutdown();
                        Console.WriteLine("STATUS|manual_shutdown_requested");
                    };

                    Console.WriteLine("STATUS|creating_engine");
                    var engineTask = Task.Run(() => new REngine(engineParams));
                    if (!engineTask.Wait(TimeSpan.FromSeconds(""" + str(ENGINE_CREATION_TIMEOUT_SECONDS) + r""")))
                    {
                        Console.WriteLine("ERROR|engine_creation_timeout");
                        return 2;
                    }
                    engine = engineTask.Result;
                    Console.WriteLine("STATUS|engine_created");

                    callbacks.RepositoryLoginStatus = ProbeLoginStatus.LoginInProgress;
                    Console.WriteLine("STATUS|repository_login_start");
                    engine.loginRepository(
                        callbacks,
                        String.Empty,
                        userName,
                        password,
                        repositoryConnectionPoint
                    );

                    DateTime repositoryLoginDeadline = DateTime.UtcNow.AddSeconds(45);
                    while (DateTime.UtcNow < repositoryLoginDeadline &&
                           callbacks.RepositoryLoginStatus != ProbeLoginStatus.LoggedIn &&
                           callbacks.RepositoryLoginStatus != ProbeLoginStatus.LoginFailed &&
                           !callbacks.ShutdownRequested)
                    {
                        Thread.Sleep(250);
                    }

                    if (callbacks.RepositoryLoginStatus != ProbeLoginStatus.LoggedIn)
                    {
                        Console.WriteLine("ERROR|repository_login_not_complete");
                        return 3;
                    }

                    Console.WriteLine("STATUS|requesting_agreements");
                    engine.listAgreements(false, null);
                    Thread.Sleep(3000);

                    Console.WriteLine("STATUS|repository_logout");
                    engine.logoutRepository();

                    Console.WriteLine("STATUS|market_data_login_start");
                    engine.login(
                        callbacks,
                        String.Empty,
                        userName,
                        password,
                        mdConnectionPoint,
                        Constants.DEFAULT_ENVIRONMENT_KEY,
                        userName,
                        password,
                        tsConnectionPoint,
                        userName,
                        password,
                        pnlConnectionPoint,
                        String.Empty,
                        String.Empty
                    );

                    DateTime tsDeadline = DateTime.UtcNow.AddSeconds(45);
                    while (DateTime.UtcNow < tsDeadline &&
                           (!callbacks.LoggedIntoMd || !callbacks.LoggedIntoTs || !callbacks.LoggedIntoPnl) &&
                           !callbacks.ShutdownRequested)
                    {
                        Thread.Sleep(250);
                    }

                    if (!callbacks.LoggedIntoTs)
                    {
                        Console.WriteLine("ERROR|trading_system_login_not_complete");
                        return 4;
                    }

                    if (!callbacks.LoggedIntoPnl)
                    {
                        Console.WriteLine(
                            "ERROR|pnl_connection_not_initialized|" +
                            "md=" + mdConnectionPoint +
                            "|ts=" + tsConnectionPoint +
                            "|pnl=" + pnlConnectionPoint +
                            "|ih=<blank>"
                        );
                        return 5;
                    }

                    DateTime accountListDeadline = DateTime.UtcNow.AddSeconds(20);
                    while (DateTime.UtcNow < accountListDeadline &&
                           callbacks.Accounts.Count == 0 &&
                           !callbacks.ShutdownRequested)
                    {
                        Thread.Sleep(250);
                    }

                    Console.WriteLine("PROBE|account_count|" + callbacks.Accounts.Count.ToString(CultureInfo.InvariantCulture));
                    foreach (AccountInfo account in callbacks.Accounts)
                    {
                        string accountId = account.AccountId == null ? String.Empty : account.AccountId;
                        Console.WriteLine("PROBE|subscribe_pnl|" + accountId);
                        try
                        {
                            engine.subscribePnl(account);
                        }
                        catch (Exception ex)
                        {
                            Console.WriteLine("PNL_SUBSCRIBE_FAILED|" + accountId + "|" + ex.Message.Replace("\r", " ").Replace("\n", " "));
                        }

                        Console.WriteLine("PROBE|replay_pnl|" + accountId);
                        try
                        {
                            engine.replayPnl(account, "account_probe_pnl");
                        }
                        catch (Exception ex)
                        {
                            Console.WriteLine("PNL_REPLAY_FAILED|" + accountId + "|" + ex.Message.Replace("\r", " ").Replace("\n", " "));
                        }
                    }

                    DateTime pnlDeadline = DateTime.UtcNow.AddSeconds(20);
                    while (DateTime.UtcNow < pnlDeadline &&
                           !callbacks.ReceivedPnlInfo &&
                           !callbacks.ShutdownRequested)
                    {
                        Thread.Sleep(250);
                    }

                    Console.WriteLine("PROBE|read_only_account_probe_complete");
                    return 0;
                }
                catch (OMException ex)
                {
                    Console.WriteLine("ERROR|om_exception|" + ex.Message.Replace("\r", " ").Replace("\n", " "));
                    return 10;
                }
                catch (Exception ex)
                {
                    Console.WriteLine("ERROR|exception|" + ex.GetType().Name + "|" + ex.Message.Replace("\r", " ").Replace("\n", " "));
                    return 11;
                }
                finally
                {
                    if (engine != null)
                    {
                        try
                        {
                            engine.logout();
                        }
                        catch
                        {
                        }

                        try
                        {
                            engine.shutdown();
                        }
                        catch
                        {
                        }
                    }
                }
            }
        }
"@

        $exitCode = [AccountProbeRunner]::Run(
            $UserName,
            $Password,
            $MdConnectionPoint,
            $TsConnectionPoint,
            $PnlConnectionPoint,
            $DiscoveredPnlCandidates,
            $RepositoryConnectionPoint
        )

        exit $exitCode
        """
    ).strip()


def write_probe_bridge():
    RITHMIC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    PROBE_BRIDGE_PATH.write_text(build_probe_bridge(), encoding="utf-8")
    return PROBE_BRIDGE_PATH


def build_command():
    dll_path = ensure_runtime_files()
    bridge_path = write_probe_bridge()
    return [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(bridge_path),
        "-DllPath",
        str(dll_path),
        "-UserName",
        RITHMIC_USER,
        "-Password",
        RITHMIC_PASSWORD,
        "-MdConnectionPoint",
        RITHMIC_MD_CONNECTION_POINT,
        "-TsConnectionPoint",
        RITHMIC_TS_CONNECTION_POINT,
        "-PnlConnectionPoint",
        RITHMIC_PNL_CONNECTION_POINT,
        "-DiscoveredPnlCandidates",
        "; ".join(DISCOVERED_PNL_CONNECTION_CANDIDATES),
        "-RepositoryConnectionPoint",
        RITHMIC_REPOSITORY_CONNECTION_POINT,
    ]


def main():
    validate_env()
    process = subprocess.Popen(
        build_command(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        cwd=str(RITHMIC_RUNTIME_DIR),
    )

    assert process.stdout is not None
    for line in process.stdout:
        sys.stdout.write(line)

    process.wait()
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
