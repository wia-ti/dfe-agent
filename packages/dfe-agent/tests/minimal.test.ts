// Minimal test para debugar hang
import { test } from "node:test";
import assert from "node:assert/strict";

test("basic 1+1=2", () => {
  assert.equal(1 + 1, 2);
});