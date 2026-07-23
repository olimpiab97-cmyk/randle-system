using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Pipes;
using System.Security.Principal;
using System.Text;

namespace RandleAI.TerminalAuthority
{
    internal static class ProvisioningClient
    {
        private static int Main(string[] args)
        {
            try
            {
                if (args.Length < 1 || args.Length > 3)
                {
                    Console.Error.WriteLine("usage: client <operation> [request-nonce] [provisioning-nonce]");
                    return 64;
                }
                string operation = NormalizeOperation(args[0]);
                string requestNonce = args.Length >= 2 ? args[1] : Guid.NewGuid().ToString("D");
                SortedDictionary<string, object> request = new SortedDictionary<string, object>(StringComparer.Ordinal);
                request["interface_version"] = AuthorityConstants.InterfaceVersion;
                request["operation"] = operation;
                request["request_nonce"] = requestNonce;
                if (operation == "ISSUE_PROVISIONING_ATTESTATION")
                {
                    if (args.Length != 3) throw new InvalidDataException("attestation requires a provisioning nonce");
                    request["provisioning_nonce"] = args[2];
                }
                else if (args.Length == 3)
                {
                    throw new InvalidDataException("unexpected provisioning nonce");
                }

                string response = Invoke(CanonicalJson.Serialize(request));
                Console.Out.WriteLine(response);
                IDictionary<string, object> parsed = StrictJson.ParseObject(response);
                string status = StrictJson.RequireString(parsed, "status");
                return String.Equals(status, "REJECTED", StringComparison.Ordinal) ? 2 : 0;
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine(exception.GetType().Name + ": " + exception.Message);
                return 70;
            }
        }

        private static string NormalizeOperation(string value)
        {
            switch (value.ToLowerInvariant())
            {
                case "health": return "GET_HEALTH";
                case "public-trust": return "GET_PUBLIC_TRUST";
                case "ledger-status": return "GET_LEDGER_STATUS";
                case "issue-nonce": return "ISSUE_PROVISIONING_NONCE";
                case "issue-attestation": return "ISSUE_PROVISIONING_ATTESTATION";
                case "self-test-unauthorized": return "SELF_TEST_UNAUTHORIZED_PRINCIPAL";
                default: return value;
            }
        }

        private static string Invoke(string request)
        {
            using (NamedPipeClientStream pipe = new NamedPipeClientStream(
                ".",
                AuthorityConstants.PipeName,
                PipeDirection.InOut,
                PipeOptions.None,
                TokenImpersonationLevel.Impersonation))
            {
                pipe.Connect(5000);
                byte[] bytes = new UTF8Encoding(false, true).GetBytes(request + "\n");
                pipe.Write(bytes, 0, bytes.Length);
                pipe.Flush();
                MemoryStream response = new MemoryStream();
                while (true)
                {
                    int value = pipe.ReadByte();
                    if (value < 0 || value == '\n') break;
                    if (response.Length >= AuthorityConstants.MaximumMessageBytes) throw new InvalidDataException("response too large");
                    response.WriteByte((byte)value);
                }
                return new UTF8Encoding(false, true).GetString(response.ToArray());
            }
        }
    }
}
