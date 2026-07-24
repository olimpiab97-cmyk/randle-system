using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.IO.Pipes;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Web.Script.Serialization;

internal static class IndependentIpcParserProbe
{
    private const string PipeName = "RandleAI.TerminalAuthority.v1";
    private const string InterfaceVersion = "3.0.0-DRAFT";
    private const int MaximumMessageBytes = 65536;

    private static string Invoke(byte[] request)
    {
        using (NamedPipeClientStream pipe = new NamedPipeClientStream(".", PipeName, PipeDirection.InOut, PipeOptions.None, TokenImpersonationLevel.Impersonation))
        {
            pipe.Connect(5000);
            pipe.ReadMode = PipeTransmissionMode.Message;
            pipe.Write(request, 0, request.Length);
            pipe.Flush();
            MemoryStream response = new MemoryStream();
            while (true)
            {
                int value = pipe.ReadByte();
                if (value < 0 || value == '\n') break;
                response.WriteByte((byte)value);
            }
            return new UTF8Encoding(false, true).GetString(response.ToArray());
        }
    }

    private static string HealthJson()
    {
        return "{\"interface_version\":\"" + InterfaceVersion + "\",\"operation\":\"GET_HEALTH\",\"request_nonce\":\"" + Guid.NewGuid().ToString("D") + "\"}";
    }

    private static byte[] Line(string text)
    {
        return new UTF8Encoding(false, true).GetBytes(text + "\n");
    }

    private static string FileSha256(string path)
    {
        using (SHA256 sha = SHA256.Create())
        using (FileStream stream = File.OpenRead(path))
        {
            byte[] hash = sha.ComputeHash(stream);
            StringBuilder value = new StringBuilder();
            foreach (byte item in hash) value.Append(item.ToString("x2", CultureInfo.InvariantCulture));
            return value.ToString();
        }
    }

    private static IDictionary<string, object> ResponseSummary(string response)
    {
        SortedDictionary<string, object> result = new SortedDictionary<string, object>(StringComparer.Ordinal);
        result["raw"] = response;
        try
        {
            JavaScriptSerializer serializer = new JavaScriptSerializer();
            IDictionary<string, object> parsed = serializer.DeserializeObject(response) as IDictionary<string, object>;
            object status;
            object error;
            result["status"] = parsed != null && parsed.TryGetValue("status", out status) ? Convert.ToString(status, CultureInfo.InvariantCulture) : "";
            result["error_code"] = parsed != null && parsed.TryGetValue("error_code", out error) ? Convert.ToString(error, CultureInfo.InvariantCulture) : "";
        }
        catch (Exception exception)
        {
            result["parse_error"] = exception.GetType().FullName;
        }
        return result;
    }

    public static int Main(string[] args)
    {
        const string checkpoint = @"C:\ProgramData\RandleAI\TerminalAuthority\Ledger\checkpoint.json";
        string checkpointBefore = FileSha256(checkpoint);
        List<object> probes = new List<object>();

        string normal = HealthJson();
        probes.Add(new SortedDictionary<string, object>(StringComparer.Ordinal) {
            { "id", "IPC-NORMAL-HEALTH" },
            { "request_bytes", Line(normal).Length },
            { "response", ResponseSummary(Invoke(Line(normal))) }
        });

        string nonce = Guid.NewGuid().ToString("D");
        string duplicateOperation = "{\"interface_version\":\"" + InterfaceVersion + "\",\"operation\":\"UNKNOWN\",\"operation\":\"GET_HEALTH\",\"request_nonce\":\"" + nonce + "\"}";
        probes.Add(new SortedDictionary<string, object>(StringComparer.Ordinal) {
            { "id", "IPC-DUPLICATE-OPERATION-LAST-WINS" },
            { "request_bytes", Line(duplicateOperation).Length },
            { "response", ResponseSummary(Invoke(Line(duplicateOperation))) }
        });

        JavaScriptSerializer localParser = new JavaScriptSerializer();
        IDictionary<string, object> duplicateLocal = (IDictionary<string, object>)localParser.DeserializeObject("{\"a\":1,\"a\":2}");
        IDictionary<string, object> coercionLocal = (IDictionary<string, object>)localParser.DeserializeObject("{\"n\":\"1\"}");
        probes.Add(new SortedDictionary<string, object>(StringComparer.Ordinal) {
            { "id", "LOCAL-JAVASCRIPTSERIALIZER-DUPLICATE-COLLAPSE" },
            { "key_count", duplicateLocal.Count },
            { "a_value", Convert.ToInt64(duplicateLocal["a"], CultureInfo.InvariantCulture) }
        });
        probes.Add(new SortedDictionary<string, object>(StringComparer.Ordinal) {
            { "id", "LOCAL-CONVERT-TO-INT64-STRING-COERCION" },
            { "converted", Convert.ToInt64(coercionLocal["n"], CultureInfo.InvariantCulture) }
        });

        string checkpointAfter = FileSha256(checkpoint);
        SortedDictionary<string, object> output = new SortedDictionary<string, object>(StringComparer.Ordinal);
        output["artifact_type"] = "R7_INDEPENDENT_IPC_PARSER_PROBE_RESULT";
        output["checkpoint_after_sha256"] = checkpointAfter;
        output["checkpoint_before_sha256"] = checkpointBefore;
        output["checkpoint_unchanged"] = String.Equals(checkpointBefore, checkpointAfter, StringComparison.Ordinal);
        output["probes"] = probes.ToArray();
        output["schema_version"] = "1.0.0";
        string json = new JavaScriptSerializer().Serialize(output);
        if (args.Length == 1) File.WriteAllText(args[0], json + "\n", new UTF8Encoding(false));
        Console.WriteLine(json);
        return 0;
    }
}
