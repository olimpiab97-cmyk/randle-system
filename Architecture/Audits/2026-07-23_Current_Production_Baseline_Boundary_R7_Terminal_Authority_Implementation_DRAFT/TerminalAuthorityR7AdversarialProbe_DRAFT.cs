using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Pipes;
using System.Linq;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;

namespace RandleAI.TerminalAuthority
{
    internal static class R7AdversarialProbe
    {
        private static int Main(string[] args)
        {
            try
            {
                if (args.Length < 1) throw new InvalidDataException("named probe required");
                string nonce = Guid.NewGuid().ToString("D");
                if (args[0] == "partial-request") return InvokePartialRequest(nonce);
                if (args[0] == "disconnect-partial") return InvokeDisconnectedPartial(nonce);
                if (args[0] == "pipe-acl") return VerifyPipeAcl(nonce);
                string request;
                if (args[0] == "malformed") request = "{not-json";
                else if (args[0] == "oversized") request = new string('x', R7Constants.MaximumMessageBytes + 1);
                else
                {
                    SortedDictionary<string, object> value = new SortedDictionary<string, object>(StringComparer.Ordinal);
                    value["interface_version"] = R7Constants.InterfaceVersion;
                    value["operation"] = "GET_HEALTH";
                    value["request_nonce"] = nonce;
                    if (args[0] == "unknown-operation") value["operation"] = "SIGN";
                    else if (args[0] == "generic-sign") { value["operation"] = "SIGN"; value["payload"] = "attacker-selected"; }
                    else if (args[0] == "extra-field") value["unexpected"] = true;
                    else if (args[0] == "ledger-root") value["ledger_root"] = @"C:\Users\Trader\attacker-ledger";
                    else if (args[0] == "trust-root") value["trust_root"] = @"C:\Users\Trader\attacker-trust";
                    else if (args[0] == "sequence") value["sequence"] = 1;
                    else if (args[0] == "prior-hash") value["prior_hash"] = R7Constants.ZeroHash;
                    else if (args[0] == "caller-status") value["status"] = "MATCHED";
                    else if (args[0] == "arbitrary-payload") value["payload"] = new SortedDictionary<string, object>(StringComparer.Ordinal) { { "status", "MATCHED" } };
                    else if (args[0] == "client-replacement-replay" || args[0] == "full-service-replay")
                    {
                        value.Clear();
                        value["attempt_id"] = new string('a', 64);
                        value["event_count"] = 0;
                        value["interface_version"] = R7Constants.InterfaceVersion;
                        value["operation"] = "EXECUTE_R7_RUN";
                        value["phase"] = "CANDIDATE";
                        value["prior_result"] = new SortedDictionary<string, object>(StringComparer.Ordinal) { { "passed", 178 }, { "status", "MATCHED" } };
                        value["process_receipts"] = new object[0];
                        value["request_nonce"] = nonce;
                        value["run_id"] = new string('b', 64);
                    }
                    else if (args[0] == "zero-process-terminal" || args[0] == "zero-event-terminal" || args[0] == "replayed-run-id")
                    {
                        value.Clear();
                        value["attempt_id"] = new string('a', 64);
                        value["interface_version"] = R7Constants.InterfaceVersion;
                        value["operation"] = "EXECUTE_R7_RUN";
                        value["phase"] = "CANDIDATE";
                        value["request_nonce"] = nonce;
                        if (args[0] == "zero-process-terminal") value["process_count"] = 0;
                        if (args[0] == "zero-event-terminal") value["event_count"] = 0;
                        if (args[0] == "replayed-run-id") value["run_id"] = new string('c', 64);
                    }
                    else if (args[0] == "unsigned-terminal-object")
                    {
                        value.Clear();
                        value["interface_version"] = R7Constants.InterfaceVersion;
                        value["locator"] = new SortedDictionary<string, object>(StringComparer.Ordinal) { { "status", "CANDIDATE_COMPLETE" } };
                        value["operation"] = "GET_R7_RECEIPT";
                        value["request_nonce"] = nonce;
                    }
                    else if (args[0] == "unresolved-terminal-locator")
                    {
                        value.Clear();
                        value["interface_version"] = R7Constants.InterfaceVersion;
                        value["locator"] = R7Support.ContentLocator("terminal", new string('d', 64));
                        value["operation"] = "GET_R7_RECEIPT";
                        value["request_nonce"] = nonce;
                    }
                    else if (args[0] == "reconcile-dictionaries")
                    {
                        value.Clear();
                        value["attempt_id"] = new string('a', 64);
                        value["candidate_locator"] = new SortedDictionary<string, object>(StringComparer.Ordinal);
                        value["fresh_locator"] = new SortedDictionary<string, object>(StringComparer.Ordinal);
                        value["interface_version"] = R7Constants.InterfaceVersion;
                        value["operation"] = "RECONCILE_R7_TERMINAL_RECEIPTS";
                        value["request_nonce"] = nonce;
                    }
                    else if (args[0] == "fabricated-match")
                    {
                        value.Clear();
                        value["candidate"] = new SortedDictionary<string, object>(StringComparer.Ordinal) { { "status", "MATCHED" } };
                        value["fresh"] = new SortedDictionary<string, object>(StringComparer.Ordinal) { { "status", "MATCHED" } };
                        value["interface_version"] = R7Constants.InterfaceVersion;
                        value["operation"] = "RECONCILE_R7_TERMINAL_RECEIPTS";
                        value["request_nonce"] = nonce;
                    }
                    else if (args[0] == "same-receipt")
                    {
                        if (args.Length != 3) throw new InvalidDataException("same-receipt requires attempt and locator");
                        value.Clear();
                        value["attempt_id"] = args[1];
                        value["candidate_locator"] = args[2];
                        value["fresh_locator"] = args[2];
                        value["interface_version"] = R7Constants.InterfaceVersion;
                        value["operation"] = "RECONCILE_R7_TERMINAL_RECEIPTS";
                        value["request_nonce"] = nonce;
                    }
                    else throw new InvalidDataException("unknown named probe");
                    request = CanonicalJson.Serialize(value);
                }
                string response = Invoke(request);
                Console.Out.WriteLine(response);
                IDictionary<string, object> parsed = StrictJson.ParseObject(response);
                return String.Equals(StrictJson.RequireString(parsed, "status"), "REJECTED", StringComparison.Ordinal) ? 0 : 3;
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine(exception.GetType().Name + ": " + exception.Message);
                return 70;
            }
        }

        private static string Invoke(string request)
        {
            using (NamedPipeClientStream pipe = new NamedPipeClientStream(".", R7Constants.PipeName, PipeDirection.InOut, PipeOptions.None, TokenImpersonationLevel.Impersonation))
            {
                pipe.Connect(10000);
                byte[] bytes = new UTF8Encoding(false, true).GetBytes(request + "\n");
                pipe.Write(bytes, 0, bytes.Length);
                pipe.Flush();
                MemoryStream response = new MemoryStream();
                while (true)
                {
                    int item = pipe.ReadByte();
                    if (item < 0 || item == '\n') break;
                    if (response.Length > R7Constants.MaximumMessageBytes * 4) throw new InvalidDataException("response too large");
                    response.WriteByte((byte)item);
                }
                return new UTF8Encoding(false, true).GetString(response.ToArray());
            }
        }

        private static int InvokePartialRequest(string nonce)
        {
            SortedDictionary<string, object> value = new SortedDictionary<string, object>(StringComparer.Ordinal);
            value["interface_version"] = R7Constants.InterfaceVersion;
            value["operation"] = "GET_HEALTH";
            value["request_nonce"] = nonce;
            byte[] bytes = new UTF8Encoding(false, true).GetBytes(CanonicalJson.Serialize(value) + "\n");
            using (NamedPipeClientStream pipe = new NamedPipeClientStream(".", R7Constants.PipeName, PipeDirection.InOut, PipeOptions.None, TokenImpersonationLevel.Impersonation))
            {
                pipe.Connect(10000);
                int first = bytes.Length / 3;
                int second = bytes.Length / 3;
                pipe.Write(bytes, 0, first);
                pipe.Flush();
                System.Threading.Thread.Sleep(100);
                pipe.Write(bytes, first, second);
                pipe.Flush();
                System.Threading.Thread.Sleep(100);
                pipe.Write(bytes, first + second, bytes.Length - first - second);
                pipe.Flush();
                string response = ReadResponse(pipe);
                Console.Out.WriteLine(response);
                IDictionary<string, object> parsed = StrictJson.ParseObject(response);
                return String.Equals(StrictJson.RequireString(parsed, "status"), "COMPLETE", StringComparison.Ordinal) &&
                    String.Equals(StrictJson.RequireString(parsed, "result_code"), "R7_AUTHORITY_HEALTHY", StringComparison.Ordinal) ? 0 : 3;
            }
        }

        private static int InvokeDisconnectedPartial(string nonce)
        {
            SortedDictionary<string, object> value = new SortedDictionary<string, object>(StringComparer.Ordinal);
            value["interface_version"] = R7Constants.InterfaceVersion;
            value["operation"] = "ISSUE_R7_ATTEMPT";
            value["configuration"] = "SHORT_AUTOCRLF_TRUE";
            value["request_nonce"] = nonce;
            byte[] bytes = new UTF8Encoding(false, true).GetBytes(CanonicalJson.Serialize(value));
            using (NamedPipeClientStream pipe = new NamedPipeClientStream(".", R7Constants.PipeName, PipeDirection.Out, PipeOptions.None, TokenImpersonationLevel.Impersonation))
            {
                pipe.Connect(10000);
                pipe.Write(bytes, 0, bytes.Length / 2);
                pipe.Flush();
            }
            Console.Out.WriteLine("{\"result_code\":\"PARTIAL_REQUEST_DISCONNECTED\",\"status\":\"COMPLETE\"}");
            return 0;
        }

        private static int VerifyPipeAcl(string nonce)
        {
            SortedDictionary<string, object> value = new SortedDictionary<string, object>(StringComparer.Ordinal);
            value["interface_version"] = R7Constants.InterfaceVersion;
            value["operation"] = "GET_HEALTH";
            value["request_nonce"] = nonce;
            using (NamedPipeClientStream pipe = new NamedPipeClientStream(".", R7Constants.PipeName, PipeDirection.InOut, PipeOptions.None, TokenImpersonationLevel.Impersonation))
            {
                pipe.Connect(10000);
                PipeSecurity security = pipe.GetAccessControl();
                AuthorizationRuleCollection rules = security.GetAccessRules(true, false, typeof(SecurityIdentifier));
                List<PipeAccessRule> explicitRules = new List<PipeAccessRule>();
                foreach (AuthorizationRule raw in rules)
                {
                    PipeAccessRule rule = raw as PipeAccessRule;
                    if (rule != null && !rule.IsInherited) explicitRules.Add(rule);
                }
                string operatorSid = R7Constants.OperatorSid;
                string serviceSid = R7Constants.ServiceSid;
                bool operatorRule = explicitRules.Any(delegate(PipeAccessRule rule) {
                    return String.Equals(rule.IdentityReference.Value, operatorSid, StringComparison.Ordinal) && rule.AccessControlType == AccessControlType.Allow &&
                        (rule.PipeAccessRights & PipeAccessRights.ReadWrite) == PipeAccessRights.ReadWrite;
                });
                bool serviceRule = explicitRules.Any(delegate(PipeAccessRule rule) {
                    return String.Equals(rule.IdentityReference.Value, serviceSid, StringComparison.Ordinal) && rule.AccessControlType == AccessControlType.Allow &&
                        (rule.PipeAccessRights & PipeAccessRights.FullControl) == PipeAccessRights.FullControl;
                });
                bool systemRule = explicitRules.Any(delegate(PipeAccessRule rule) {
                    return String.Equals(rule.IdentityReference.Value, R7Constants.SystemSid, StringComparison.Ordinal) && rule.AccessControlType == AccessControlType.Allow &&
                        (rule.PipeAccessRights & PipeAccessRights.FullControl) == PipeAccessRights.FullControl;
                });
                bool broadRule = explicitRules.Any(delegate(PipeAccessRule rule) {
                    string sid = rule.IdentityReference.Value;
                    return sid == "S-1-1-0" || sid == "S-1-5-11" || sid == "S-1-5-32-545" || sid == "S-1-5-32-544";
                });
                byte[] bytes = new UTF8Encoding(false, true).GetBytes(CanonicalJson.Serialize(value) + "\n");
                pipe.Write(bytes, 0, bytes.Length);
                pipe.Flush();
                string response = ReadResponse(pipe);
                SortedDictionary<string, object> result = new SortedDictionary<string, object>(StringComparer.Ordinal);
                result["access_rule_count"] = explicitRules.Count;
                result["broad_rule_absent"] = !broadRule;
                result["operator_rule"] = operatorRule;
                result["protected"] = security.AreAccessRulesProtected;
                result["sddl"] = security.GetSecurityDescriptorSddlForm(AccessControlSections.All);
                result["service_rule"] = serviceRule;
                result["status"] = "COMPLETE";
                result["system_rule"] = systemRule;
                Console.Out.WriteLine(CanonicalJson.Serialize(result));
                IDictionary<string, object> parsed = StrictJson.ParseObject(response);
                return security.AreAccessRulesProtected && explicitRules.Count == 3 && operatorRule && serviceRule && systemRule && !broadRule &&
                    String.Equals(StrictJson.RequireString(parsed, "status"), "COMPLETE", StringComparison.Ordinal) ? 0 : 3;
            }
        }

        private static string ReadResponse(Stream pipe)
        {
            MemoryStream response = new MemoryStream();
            while (true)
            {
                int item = pipe.ReadByte();
                if (item < 0 || item == '\n') break;
                if (response.Length > R7Constants.MaximumMessageBytes * 4) throw new InvalidDataException("response too large");
                response.WriteByte((byte)item);
            }
            return new UTF8Encoding(false, true).GetString(response.ToArray());
        }
    }
}
