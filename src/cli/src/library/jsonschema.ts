// A small JSON Schema (draft-07 subset) checker, enough for src/schemas/retrieval-row.schema.json: type,
// enum, const, required, properties, additionalProperties:false, items, oneOf, $ref to #/definitions/*,
// minimum/maximum, minLength/maxLength and pattern. It exists so the ledger can check every row against the
// shipped schema file without a runtime dependency; a Python test checks the same schema with `jsonschema`.
export type JsonSchema = { [key: string]: unknown };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function typeOf(value: unknown): string {
  if (value === null) return 'null';
  if (Array.isArray(value)) return 'array';
  if (typeof value === 'number') return Number.isInteger(value) ? 'integer' : 'number';
  return typeof value;
}

function typeMatches(want: string, value: unknown): boolean {
  const got = typeOf(value);
  return want === got || (want === 'number' && got === 'integer');
}

function resolveRef(root: JsonSchema, ref: string): JsonSchema | undefined {
  if (!ref.startsWith('#/')) return undefined;
  let node: unknown = root;
  for (const part of ref.slice(2).split('/')) node = isRecord(node) ? node[part] : undefined;
  return isRecord(node) ? node : undefined;
}

/** Problems found, as short messages with the path ("primary.latency_ms: expected integer"). Empty means valid. */
export function checkSchema(schema: JsonSchema, value: unknown, root: JsonSchema = schema, path = ''): string[] {
  const here = path || 'row';
  if (typeof schema.$ref === 'string') {
    const target = resolveRef(root, schema.$ref);
    return target ? checkSchema(target, value, root, path) : [`${here}: unknown reference ${schema.$ref}`];
  }
  if (Array.isArray(schema.oneOf)) {
    const options = schema.oneOf.filter(isRecord);
    const results = options.map((option) => checkSchema(option, value, root, path));
    const passing = results.filter((problems) => problems.length === 0).length;
    if (passing === 1) return [];
    if (passing > 1) return [`${here}: matches more than one option`];
    // Report the problems of the option closest to the row (the one with the fewest).
    const best = results.reduce((a, b) => (b.length < a.length ? b : a), results[0] ?? [`${here}: no option matches`]);
    return best;
  }
  const problems: string[] = [];
  if ('const' in schema && schema.const !== value) problems.push(`${here}: expected ${JSON.stringify(schema.const)}`);
  if (Array.isArray(schema.enum) && !schema.enum.includes(value)) problems.push(`${here}: not one of ${schema.enum.map((item) => JSON.stringify(item)).join(', ')}`);
  if (schema.type !== undefined) {
    const wanted = (Array.isArray(schema.type) ? schema.type : [schema.type]).filter((item): item is string => typeof item === 'string');
    if (!wanted.some((name) => typeMatches(name, value))) return [`${here}: expected ${wanted.join(' or ')}`];
  }
  if (typeof value === 'number') {
    if (typeof schema.minimum === 'number' && value < schema.minimum) problems.push(`${here}: below ${schema.minimum}`);
    if (typeof schema.maximum === 'number' && value > schema.maximum) problems.push(`${here}: above ${schema.maximum}`);
  }
  if (typeof value === 'string') {
    if (typeof schema.minLength === 'number' && value.length < schema.minLength) problems.push(`${here}: too short`);
    if (typeof schema.maxLength === 'number' && value.length > schema.maxLength) problems.push(`${here}: too long`);
    if (typeof schema.pattern === 'string' && !new RegExp(schema.pattern, 'u').test(value)) problems.push(`${here}: does not match ${schema.pattern}`);
  }
  if (Array.isArray(value) && isRecord(schema.items)) {
    value.forEach((item, index) => problems.push(...checkSchema(schema.items as JsonSchema, item, root, `${path}[${index}]`)));
  }
  if (isRecord(value)) {
    const properties = isRecord(schema.properties) ? schema.properties : {};
    if (Array.isArray(schema.required)) {
      for (const key of schema.required) if (typeof key === 'string' && !(key in value)) problems.push(`${path ? `${path}.` : ''}${key}: missing`);
    }
    for (const [key, item] of Object.entries(value)) {
      const child = properties[key];
      const next = path ? `${path}.${key}` : key;
      if (isRecord(child)) problems.push(...checkSchema(child, item, root, next));
      else if (schema.additionalProperties === false) problems.push(`${next}: not allowed`);
    }
  }
  return problems;
}
