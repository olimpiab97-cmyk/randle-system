import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

from rithmic_live_listener import (
    ENGINE_CREATION_TIMEOUT_SECONDS,
    RITHMIC_CACHE_DIR,
    RITHMIC_MD_CONNECTION_POINT,
    RITHMIC_PASSWORD,
    RITHMIC_REPOSITORY_CONNECTION_POINT,
    RITHMIC_RUNTIME_DIR,
    RITHMIC_TS_CONNECTION_POINT,
    RITHMIC_USER,
    ensure_runtime_files,
)


DISCOVERY_BRIDGE_PATH = RITHMIC_CACHE_DIR / "rithmic_symbol_discovery.ps1"
DISCOVERY_QUERIES = (
    ("CME", "RTY"),
    ("CME", "RUSSELL"),
    ("CME", "E-MINI RUSSELL"),
    ("CME", "RUSSELL 2000"),
)


def build_discovery_bridge():
    query_lines = []
    for exchange, term in DISCOVERY_QUERIES:
        query_lines.append(
            '                    RunInstrumentSearch(engine, "{exchange}", "{term}");\n'
            '                    Thread.Sleep(3000);'.format(
                exchange=exchange,
                term=term.replace('"', '\\"'),
            )
        )

    queries_code = "\n".join(query_lines)

    return textwrap.dedent(
        r"""
        param(
            [string]$DllPath,
            [string]$UserName,
            [string]$Password,
            [string]$MdConnectionPoint,
            [string]$TsConnectionPoint,
            [string]$RepositoryConnectionPoint
        )

        $ErrorActionPreference = "Stop"

        Add-Type -Path $DllPath

        Add-Type -ReferencedAssemblies @($DllPath) -TypeDefinition @"
        using System;
        using System.Collections;
        using System.Collections.Generic;
        using System.Collections.ObjectModel;
        using System.Reflection;
        using System.Text;
        using System.Threading;
        using System.Threading.Tasks;
        using com.omnesys.omne.om;
        using com.omnesys.rapi;

        public enum DiscoveryLoginStatus
        {
            NotLoggedIn,
            LoginInProgress,
            LoginFailed,
            LoggedIn
        }

        public class DiscoveryAdmCallbacks : AdmCallbacks
        {
            public override void Alert(AlertInfo info)
            {
                var sb = new StringBuilder();
                info.Dump(sb);
                Console.WriteLine("ADM|" + sb.ToString().Replace("\r", " ").Replace("\n", " "));
            }
        }

        public class DiscoveryCallbacks : RCallbacks
        {
            public DiscoveryLoginStatus RepositoryLoginStatus = DiscoveryLoginStatus.NotLoggedIn;
            public bool ReceivedAgreementList = false;
            public int UnacceptedMandatoryAgreementCount = 0;
            public bool LoggedIntoMd = false;
            public bool LoggedIntoTs = false;
            public bool MarketDataClosedUnexpectedly = false;
            public bool TradingSystemClosedUnexpectedly = false;
            public bool ShutdownRequested = false;
            public List<AccountInfo> Accounts = new List<AccountInfo>();

            private static string FormatValue(object value)
            {
                if (value == null)
                {
                    return "<null>";
                }

                if (value is string)
                {
                    return value.ToString();
                }

                IEnumerable enumerable = value as IEnumerable;
                if (!(value is string) && enumerable != null)
                {
                    List<string> items = new List<string>();
                    int count = 0;
                    foreach (object item in enumerable)
                    {
                        if (item == null)
                        {
                            items.Add("<null>");
                        }
                        else if (item.GetType().IsPrimitive || item is decimal || item is string)
                        {
                            items.Add(item.ToString());
                        }
                        else
                        {
                            items.Add(FormatObject(item));
                        }

                        count++;
                        if (count >= 10)
                        {
                            items.Add("...");
                            break;
                        }
                    }

                    return "[" + String.Join(", ", items.ToArray()) + "]";
                }

                if (value.GetType().IsPrimitive || value is decimal)
                {
                    return value.ToString();
                }

                return FormatObject(value);
            }

            private static string FormatObject(object info)
            {
                if (info == null)
                {
                    return "<null>";
                }

                Type type = info.GetType();
                List<string> parts = new List<string>();
                foreach (PropertyInfo property in type.GetProperties(BindingFlags.Public | BindingFlags.Instance))
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
                        value = "<error:" + ex.GetType().Name + ">";
                    }

                    parts.Add(property.Name + "=" + FormatValue(value));
                }

                return type.Name + "{" + String.Join(";", parts.ToArray()) + "}";
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

                if (alertText.IndexOf("Repository Connection Login Complete", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    RepositoryLoginStatus = DiscoveryLoginStatus.LoggedIn;
                    Console.WriteLine("STATUS|repository_login_complete");
                }
                else if (alertText.IndexOf("Repository Connection Failed", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    RepositoryLoginStatus = DiscoveryLoginStatus.LoginFailed;
                    Console.WriteLine("STATUS|repository_login_failed");
                }
                else if (alertText.IndexOf("Market Data Connection Login Complete", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    LoggedIntoMd = true;
                    Console.WriteLine("STATUS|market_data_login_complete");
                }
                else if (alertText.IndexOf("Trading System Connection Login Complete", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    LoggedIntoTs = true;
                    Console.WriteLine("STATUS|trading_system_login_complete");
                }
                else if (alertText.IndexOf("Market Data Connection Closed", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    MarketDataClosedUnexpectedly = true;
                    Console.WriteLine("STATUS|market_data_connection_closed_unexpected");
                }
                else if (alertText.IndexOf("Trading System Connection Closed", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    TradingSystemClosedUnexpectedly = true;
                    Console.WriteLine("STATUS|trading_system_connection_closed_unexpected");
                }
            }

            public override void AgreementList(AgreementListInfo info)
            {
                foreach (AgreementInfo agreement in info.Agreements)
                {
                    if (agreement.Mandatory && agreement.Status == "active")
                    {
                        UnacceptedMandatoryAgreementCount++;
                    }
                }

                ReceivedAgreementList = true;
                Console.WriteLine("STATUS|agreement_list_received|" + UnacceptedMandatoryAgreementCount);
            }

            public override void AccountList(AccountListInfo info)
            {
                Console.WriteLine("ACCOUNT_LIST|" + FormatObject(info));
                if (info.Accounts == null)
                {
                    return;
                }

                Accounts.Clear();
                foreach (AccountInfo account in info.Accounts)
                {
                    Accounts.Add(account);
                    Console.WriteLine(
                        "ACCOUNT|" +
                        "account_id=" + FormatValue(account.AccountId) + "|" +
                        "account_name=" + FormatValue(account.AccountName) + "|" +
                        "fcm_id=" + FormatValue(account.FcmId) + "|" +
                        "ib_id=" + FormatValue(account.IbId)
                    );
                }
            }

            public override void ExchangeList(ExchangeListInfo info)
            {
                Console.WriteLine("EXCHANGE_LIST|" + FormatObject(info));
            }

            public override void InstrumentSearch(InstrumentSearchInfo info)
            {
                Console.WriteLine("INSTRUMENT_SEARCH|" + FormatObject(info));
                if (info.Instruments == null)
                {
                    return;
                }

                foreach (RefDataInfo instrument in info.Instruments)
                {
                    string productCode = instrument.ProductCode == null ? String.Empty : instrument.ProductCode.Trim().ToUpperInvariant();
                    string description = instrument.Description == null ? String.Empty : instrument.Description.Trim();
                    string symbol = instrument.Symbol == null ? String.Empty : instrument.Symbol.Trim().ToUpperInvariant();
                    string descriptionUpper = description.ToUpperInvariant();
                    bool isRtyCandidate =
                        productCode == "RTY" ||
                        productCode == "M2K" ||
                        descriptionUpper.IndexOf("RUSSELL", StringComparison.OrdinalIgnoreCase) >= 0 ||
                        descriptionUpper.IndexOf("RUSSELL 2000", StringComparison.OrdinalIgnoreCase) >= 0;

                    if (!isRtyCandidate)
                    {
                        continue;
                    }

                    Console.WriteLine(
                        "SEARCH_CANDIDATE|" +
                        "exchange=" + instrument.Exchange + "|" +
                        "symbol=" + symbol + "|" +
                        "product_code=" + productCode + "|" +
                        "description=" + description.Replace("\r", " ").Replace("\n", " ") + "|" +
                        "expiration=" + instrument.Expiration + "|" +
                        "tradable=" + FormatValue(instrument.IsTradable) + "|" +
                        "context=" + info.Context
                    );
                }
            }

            public override void InstrumentByUnderlying(InstrumentByUnderlyingInfo info)
            {
                Console.WriteLine("INSTRUMENT_BY_UNDERLYING|" + FormatObject(info));
            }

            public override void RefData(RefDataInfo info)
            {
                Console.WriteLine("REFDATA|" + FormatObject(info));
            }

            public override void ProductRmsList(ProductRmsListInfo info)
            {
                Console.WriteLine("PRODUCT_RMS_LIST|" + FormatObject(info));
            }

            public override void TradeRouteList(TradeRouteListInfo info)
            {
                Console.WriteLine("TRADE_ROUTE_LIST|" + FormatObject(info));
            }
        }

        public static class DiscoveryRunner
        {
            private static void RunInstrumentSearch(REngine engine, string exchange, string term)
            {
                SearchTerm searchTerm = new SearchTerm(term);
                ReadOnlyCollection<SearchTerm> terms =
                    new ReadOnlyCollection<SearchTerm>(new List<SearchTerm> { searchTerm });
                string context = "search|" + exchange + "|" + term;
                Console.WriteLine("SEARCH_REQUEST|" + context);
                try
                {
                    engine.searchInstrument(exchange, terms, context);
                }
                catch (Exception ex)
                {
                    Console.WriteLine("SEARCH_REQUEST_FAILED|" + context + "|" + ex.Message.Replace("\r", " ").Replace("\n", " "));
                }
            }

            private static void RunUnderlyingRequest(REngine engine, string exchange, string key1, string key2)
            {
                string context = "underlying|" + exchange + "|" + key1 + "|" + key2;
                Console.WriteLine("UNDERLYING_REQUEST|" + context);
                try
                {
                    engine.getInstrumentByUnderlying(exchange, key1, key2, context);
                }
                catch (Exception ex)
                {
                    Console.WriteLine("UNDERLYING_REQUEST_FAILED|" + context + "|" + ex.Message.Replace("\r", " ").Replace("\n", " "));
                }
            }

            public static int Run(
                string userName,
                string password,
                string mdConnectionPoint,
                string tsConnectionPoint,
                string repositoryConnectionPoint)
            {
                DiscoveryCallbacks callbacks = new DiscoveryCallbacks();
                REngineParams engineParams = new REngineParams();
                REngine engine = null;

                engineParams.AppName = "RithmicSymbolDiscovery";
                engineParams.AppVersion = "1.0.0.0";
                engineParams.AdmCallbacks = new DiscoveryAdmCallbacks();
                engineParams.DmnSrvrAddr = "ritpz01004.01.rithmic.com:65000~ritpz04063.04.rithmic.com:65000~ritpz01004.01.rithmic.net:65000~ritpz04063.04.rithmic.net:65000~ritpz01004.01.theomne.net:65000~ritpz04063.04.theomne.net:65000~ritpz01004.01.theomne.com:65000~ritpz04063.04.theomne.com:65000";
                engineParams.DomainName = "rithmic_paper_prod_domain";
                engineParams.LicSrvrAddr = "ritpz04063.04.rithmic.com:56000~ritpz01004.01.rithmic.com:56000~ritpz04063.04.rithmic.net:56000~ritpz04063.04.theomne.net:56000~ritpz04063.04.theomne.com:56000~ritpz01000.01.rithmic.com:56000~ritpz01001.01.rithmic.com:56000~ritpz01000.01.rithmic.net:56000~ritpz01001.01.rithmic.net:56000~ritpz01000.01.theomne.net:56000~ritpz01001.01.theomne.net:56000~ritpz01000.01.theomne.com:56000~ritpz01001.01.theomne.com:56000~ritpz24050.rithmic.com:56000~ritpz24050.rithmic.net:56000~ritpz24050.theomne.net:56000~ritpz24050.theomne.com:56000~ritpz23010.rithmic.com:56000~ritpz23010.rithmic.net:56000~ritpz23010.theomne.net:56000~ritpz23010.theomne.com:56000~ritpz23011.rithmic.com:56000~ritpz23011.rithmic.net:56000~ritpz23011.theomne.net:56000~ritpz23011.theomne.com:56000~ritpz24013.rithmic.com:56000~ritpz24013.rithmic.net:56000~ritpz24013.theomne.net:56000~ritpz24013.theomne.com:56000";
                engineParams.LocBrokAddr = "ritpz04063.04.rithmic.com:64100";
                engineParams.LoggerAddr = "ritpz04063.04.rithmic.com:45454~ritpz01004.01.rithmic.com:45454~ritpz04063.04.rithmic.net:45454~ritpz01004.01.rithmic.net:45454~ritpz04063.04.theomne.net:45454~ritpz01004.01.theomne.net:45454~ritpz04063.04.theomne.com:45454~ritpz01004.01.theomne.com:45454";
                engineParams.LogFilePath = "rithmic_symbol_discovery.log";

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
                        return 12;
                    }

                    engine = engineTask.Result;
                    Console.WriteLine("STATUS|dll_loaded");

                    callbacks.RepositoryLoginStatus = DiscoveryLoginStatus.LoginInProgress;
                    Console.WriteLine("STATUS|repository_login_start");
                    engine.loginRepository(callbacks, String.Empty, userName, password, repositoryConnectionPoint);

                    while (callbacks.RepositoryLoginStatus != DiscoveryLoginStatus.LoggedIn &&
                           callbacks.RepositoryLoginStatus != DiscoveryLoginStatus.LoginFailed)
                    {
                        if (callbacks.ShutdownRequested)
                        {
                            return 0;
                        }
                        Thread.Sleep(250);
                    }

                    if (callbacks.RepositoryLoginStatus == DiscoveryLoginStatus.LoginFailed)
                    {
                        Console.WriteLine("ERROR|repository_login_failed");
                        engine.shutdown();
                        return 2;
                    }

                    Console.WriteLine("STATUS|requesting_agreements");
                    engine.listAgreements(false, null);
                    while (!callbacks.ReceivedAgreementList)
                    {
                        if (callbacks.ShutdownRequested)
                        {
                            return 0;
                        }
                        Thread.Sleep(250);
                    }

                    if (callbacks.UnacceptedMandatoryAgreementCount > 0)
                    {
                        Console.WriteLine("ERROR|mandatory_agreements_unaccepted");
                        engine.logoutRepository();
                        engine.shutdown();
                        return 3;
                    }

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
                        String.Empty,
                        String.Empty,
                        String.Empty,
                        String.Empty,
                        String.Empty
                    );

                    while (!callbacks.LoggedIntoMd || !callbacks.LoggedIntoTs)
                    {
                        if (callbacks.ShutdownRequested)
                        {
                            return 0;
                        }
                        Thread.Sleep(250);
                    }

                    Console.WriteLine("STATUS|lookup_begin");
                    engine.listTradeRoutes("trade_routes");
                    engine.listExchanges("exchange_list");
                    Thread.Sleep(3000);
                    foreach (AccountInfo account in callbacks.Accounts)
                    {
                        string accountId = account.AccountId == null ? String.Empty : account.AccountId;
                        Console.WriteLine("PRODUCT_RMS_REQUEST|" + accountId);
                        try
                        {
                            engine.getProductRmsInfo(account, "product_rms|" + accountId);
                        }
                        catch (Exception ex)
                        {
                            Console.WriteLine("PRODUCT_RMS_REQUEST_FAILED|" + accountId + "|" + ex.Message.Replace("\r", " ").Replace("\n", " "));
                        }
                        Thread.Sleep(3000);
                    }
        """ + queries_code + r"""
                    RunUnderlyingRequest(engine, "CME", "RTY", "RTY");
                    Thread.Sleep(3000);

                    DateTime deadline = DateTime.UtcNow.AddSeconds(20);
                    while (DateTime.UtcNow < deadline &&
                           !callbacks.ShutdownRequested &&
                           !callbacks.MarketDataClosedUnexpectedly &&
                           !callbacks.TradingSystemClosedUnexpectedly)
                    {
                        Thread.Sleep(250);
                    }

                    Console.WriteLine("STATUS|lookup_complete");
                    return 0;
                }
                catch (OMException ex)
                {
                    Console.WriteLine("ERROR|" + ex.Message.Replace("\r", " ").Replace("\n", " "));
                    return 10;
                }
                catch (Exception ex)
                {
                    Console.WriteLine("ERROR|" + ex.Message.Replace("\r", " ").Replace("\n", " "));
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

        $exitCode = [DiscoveryRunner]::Run(
            $UserName,
            $Password,
            $MdConnectionPoint,
            $TsConnectionPoint,
            $RepositoryConnectionPoint
        )

        exit $exitCode
        """
    ).strip()


def write_discovery_bridge():
    RITHMIC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    DISCOVERY_BRIDGE_PATH.write_text(build_discovery_bridge(), encoding="utf-8")
    return DISCOVERY_BRIDGE_PATH


def validate_env():
    missing = []
    if not RITHMIC_USER:
        missing.append("RITHMIC_USER")
    if not RITHMIC_PASSWORD:
        missing.append("RITHMIC_PASSWORD")
    if missing:
        raise RuntimeError("Missing required environment variables: " + ", ".join(missing))


def build_command():
    dll_path = ensure_runtime_files()
    bridge_path = write_discovery_bridge()
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
