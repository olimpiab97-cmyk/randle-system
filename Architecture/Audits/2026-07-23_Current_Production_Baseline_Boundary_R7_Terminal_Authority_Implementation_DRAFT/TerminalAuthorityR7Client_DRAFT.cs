using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Pipes;
using System.Security.Principal;
using System.Text;

namespace RandleAI.TerminalAuthority
{
    internal static class R7PublicClient
    {
        private static int Main(string[] args)
        {
            try
            {
                if (args.Length < 1) throw new InvalidDataException("operation required");
                string operation = args[0].ToLowerInvariant();
                SortedDictionary<string, object> request = new SortedDictionary<string, object>(StringComparer.Ordinal);
                request["interface_version"] = R7Constants.InterfaceVersion;
                request["request_nonce"] = Guid.NewGuid().ToString("D");
                if (operation == "health" || operation == "public-trust" || operation == "ledger-status")
                {
                    if (args.Length > 2) throw new InvalidDataException("unexpected argument");
                    request["operation"] = operation == "health" ? "GET_HEALTH" : operation == "public-trust" ? "GET_PUBLIC_TRUST" : "GET_LEDGER_STATUS";
                    if (args.Length == 2) request["request_nonce"] = RequireGuid(args[1]);
                }
                else if (operation == "issue-attempt")
                {
                    if (args.Length < 2 || args.Length > 3) throw new InvalidDataException("issue-attempt requires configuration [nonce]");
                    request["configuration"] = RequireConfiguration(args[1]);
                    request["operation"] = "ISSUE_R7_ATTEMPT";
                    if (args.Length == 3) request["request_nonce"] = RequireGuid(args[2]);
                }
                else if (operation == "execute-run")
                {
                    if (args.Length < 3 || args.Length > 4) throw new InvalidDataException("execute-run requires attempt phase [nonce]");
                    request["attempt_id"] = RequireHex(args[1]);
                    request["operation"] = "EXECUTE_R7_RUN";
                    request["phase"] = RequirePhase(args[2]);
                    if (args.Length == 4) request["request_nonce"] = RequireGuid(args[3]);
                }
                else if (operation == "reconcile")
                {
                    if (args.Length < 4 || args.Length > 5) throw new InvalidDataException("reconcile requires attempt candidate-locator fresh-locator [nonce]");
                    request["attempt_id"] = RequireHex(args[1]);
                    request["candidate_locator"] = RequireLocator(args[2], "terminal");
                    request["fresh_locator"] = RequireLocator(args[3], "terminal");
                    request["operation"] = "RECONCILE_R7_TERMINAL_RECEIPTS";
                    if (args.Length == 5) request["request_nonce"] = RequireGuid(args[4]);
                }
                else if (operation == "get-terminal" || operation == "get-reconciliation")
                {
                    if (args.Length < 2 || args.Length > 3) throw new InvalidDataException("retrieval requires immutable locator [nonce]");
                    string kind = operation == "get-terminal" ? "terminal" : "reconciliation";
                    request["locator"] = RequireLocator(args[1], kind);
                    request["operation"] = kind == "terminal" ? "GET_R7_RECEIPT" : "GET_R7_RECONCILIATION";
                    if (args.Length == 3) request["request_nonce"] = RequireGuid(args[2]);
                }
                else throw new InvalidDataException("operation not allowed");

                string response = Invoke(CanonicalJson.Serialize(request));
                Console.Out.WriteLine(response);
                IDictionary<string, object> parsed = StrictJson.ParseObject(response);
                return String.Equals(StrictJson.RequireString(parsed, "status"), "REJECTED", StringComparison.Ordinal) ? 2 : 0;
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine(exception.GetType().Name + ": " + exception.Message);
                return 70;
            }
        }

        private static string RequireConfiguration(string value)
        {
            string upper = value.ToUpperInvariant();
            string[] allowed = new string[] { "SHORT_AUTOCRLF_TRUE", "SHORT_AUTOCRLF_FALSE", "LONG_AUTOCRLF_TRUE", "LONG_AUTOCRLF_FALSE" };
            foreach (string item in allowed) if (String.Equals(upper, item, StringComparison.Ordinal)) return item;
            throw new InvalidDataException("configuration rejected");
        }

        private static string RequirePhase(string value)
        {
            string upper = value.ToUpperInvariant();
            if (upper != "CANDIDATE" && upper != "FRESH") throw new InvalidDataException("phase rejected");
            return upper;
        }

        private static string RequireGuid(string value)
        {
            Guid parsed;
            if (!Guid.TryParseExact(value, "D", out parsed) || !String.Equals(parsed.ToString("D"), value, StringComparison.Ordinal)) throw new InvalidDataException("nonce rejected");
            return value;
        }

        private static string RequireHex(string value)
        {
            if (!R7Support.IsLowerHex(value, 64)) throw new InvalidDataException("identity rejected");
            return value;
        }

        private static string RequireLocator(string value, string kind)
        {
            R7Support.ParseLocator(value, kind);
            return value;
        }

        private static string Invoke(string request)
        {
            using (NamedPipeClientStream pipe = new NamedPipeClientStream(".", R7Constants.PipeName, PipeDirection.InOut, PipeOptions.None, TokenImpersonationLevel.Impersonation))
            {
                pipe.Connect(10000);
                pipe.ReadMode = PipeTransmissionMode.Message;
                byte[] bytes = new UTF8Encoding(false, true).GetBytes(request + "\n");
                pipe.Write(bytes, 0, bytes.Length);
                pipe.Flush();
                MemoryStream response = new MemoryStream();
                while (true)
                {
                    int value = pipe.ReadByte();
                    if (value < 0 || value == '\n') break;
                    if (response.Length >= R7Constants.MaximumMessageBytes * 4) throw new InvalidDataException("response too large");
                    response.WriteByte((byte)value);
                }
                return new UTF8Encoding(false, true).GetString(response.ToArray());
            }
        }
    }
}
