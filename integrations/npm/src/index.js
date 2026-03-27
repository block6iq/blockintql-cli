/**
 * BlockINTQL JavaScript SDK
 * Sovereign blockchain intelligence for AI agents
 *
 * Privacy: Provider keys never leave your environment.
 * BlockINTQL only receives the address being screened.
 *
 * Usage:
 *   const { BlockINTQL } = require('blockintql')
 *   const client = new BlockINTQL({ apiKey: 'biq_sk_live_...' })
 *   const result = await client.screen('1A1zP1e...')
 */

const API_BASE = process.env.BLOCKINTQL_API_URL ||
  'https://btc-index-api-385334043904.us-central1.run.app'

class BlockINTQL {
  constructor({ apiKey, providerKey, provider } = {}) {
    this.apiKey = apiKey || process.env.BLOCKINTQL_API_KEY
    this.providerKey = providerKey || process.env.BLOCKINTQL_PROVIDER_KEY
    this.provider = provider
    if (!this.apiKey) throw new Error('BlockINTQL API key required')
  }

  get _headers() {
    return {
      'Authorization': `Bearer ${this.apiKey}`,
      'Content-Type': 'application/json'
    }
  }

  async _post(path, body) {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: this._headers,
      body: JSON.stringify(body)
    })
    return res.json()
  }

  async _get(path, params = {}) {
    const url = new URL(`${API_BASE}${path}`)
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
    const res = await fetch(url, { headers: this._headers })
    return res.json()
  }

  /** Get CLEAR/CAUTION/BLOCK verdict for any address */
  async verdict(address, { chain = 'bitcoin', context = '' } = {}) {
    return this._post('/v1/verdict', { address, chain, context })
  }

  /** Screen a counterparty before transacting */
  async screen(address, { chain = 'bitcoin' } = {}) {
    // PRIVACY: BlockINTQL receives address+chain ONLY
    return this._post('/v1/screen', { address, chain })
  }

  /** Run autonomous multi-agent analysis */
  async analyze(query, { addresses = [], chain = 'ethereum' } = {}) {
    return this._post('/v1/analyze', { query, addresses, chain })
  }

  /** Search OP_RETURN identity graph */
  async profile(identifier, { type = 'auto' } = {}) {
    return this._get('/v1/profile/search', { identifier, type })
  }

  /** Trace funds with FIFO/LIFO accounting */
  async trace(txid, { hops = 5, method = 'fifo' } = {}) {
    return this._post('/v1/trace', { txid, hops, method })
  }

  /** Natural language blockchain intelligence */
  async query(query) {
    return this._post('/v1/intelligence/search', { query })
  }

  /** Quick safety check — returns boolean */
  async isSafe(address, chain = 'bitcoin') {
    const result = await this.screen(address, { chain })
    return result.safe === true
  }

  /** Block payment if unsafe — throws if BLOCK verdict */
  async requireSafe(address, chain = 'bitcoin') {
    const result = await this.screen(address, { chain })
    if (!result.safe) {
      throw new Error(`Payment blocked: ${result.verdict} — ${result.risk_indicators?.join(', ')}`)
    }
    return result
  }
}

// LangChain-compatible tool definitions
const blockintqlLangChainTools = (apiKey) => {
  const client = new BlockINTQL({ apiKey })
  return [
    {
      name: 'blockintql_screen',
      description: 'Screen a blockchain address before transacting. Returns CLEAR/CAUTION/BLOCK verdict.',
      parameters: {
        type: 'object',
        properties: {
          address: { type: 'string', description: 'Bitcoin or Ethereum address' },
          chain: { type: 'string', enum: ['bitcoin', 'ethereum'], default: 'bitcoin' }
        },
        required: ['address']
      },
      execute: ({ address, chain }) => client.screen(address, { chain })
    },
    {
      name: 'blockintql_analyze',
      description: 'Run multi-agent blockchain analysis. Use for complex investigations.',
      parameters: {
        type: 'object',
        properties: {
          query: { type: 'string', description: 'Natural language analysis query' },
          addresses: { type: 'array', items: { type: 'string' } }
        },
        required: ['query']
      },
      execute: ({ query, addresses }) => client.analyze(query, { addresses })
    },
    {
      name: 'blockintql_profile',
      description: 'Search identity graph for emails/handles linked to crypto addresses.',
      parameters: {
        type: 'object',
        properties: {
          identifier: { type: 'string', description: 'Email, telegram handle, or username' }
        },
        required: ['identifier']
      },
      execute: ({ identifier }) => client.profile(identifier)
    }
  ]
}

module.exports = { BlockINTQL, blockintqlLangChainTools }
