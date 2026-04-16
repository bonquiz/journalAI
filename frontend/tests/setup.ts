// Patch jsdom's Blob with Node's Blob, which supports .stream(),
// so that `new Response(blob, ...)` works in the test environment.
import { Blob as NodeBlob } from "buffer";

if (typeof (globalThis.Blob.prototype as { stream?: unknown }).stream !== "function") {
  globalThis.Blob = NodeBlob as unknown as typeof Blob;
}
