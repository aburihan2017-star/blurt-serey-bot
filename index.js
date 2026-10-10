const fs = require('fs');
const axios = require('axios');
const serey = require('sereyjs');

// কনফিগারেশন
const BLURT_USER = 'aburihan1';
const SEREY_USER = process.env.SEREY_USERNAME || 'raihan123';
const SEREY_POSTING_KEY = process.env.SEREY_POSTING_KEY;

const DATA_FILE = 'automation_data.json';
const MAX_DAILY_POSTS = 2;
const DAY_IN_MS = 86400 * 1000;

const SEREY_CHAIN_ID = '5205c25d3e87cb3e8e527e6fbbf324b7b2b9fe7a7192c604ce5b174d08987324';
const SEREY_PREFIX = 'SRY';

// সেরি চেইন কনফিগ সেট
serey.config.set('address_prefix', SEREY_PREFIX);
serey.config.set('chain_id', SEREY_CHAIN_ID);

const BLURT_NODES = [
  'https://blurt-rpc.saboin.com',
  'https://rpc.blurt.one',
  'https://blurt.world',
];

async function blurtCall(method, params) {
  const payload = { jsonrpc: '2.0', method, params, id: 1 };
  for (const node of BLURT_NODES) {
    try {
      const res = await axios.post(node, payload, { timeout: 10000 });
      if (res.data && res.data.result) return res.data.result;
    } catch (e) {
      continue;
    }
  }
  return null;
}

function loadData() {
  if (fs.existsSync(DATA_FILE)) {
    try {
      return JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
    } catch (e) {}
  }
  return { queue: [], posted: [], timestamps: [] };
}

function saveData(data) {
  fs.writeFileSync(DATA_FILE, JSON.stringify(data, null, 2));
}

async function fetchOneYearOldPosts(postedSet) {
  const oneYearAgo = new Date(Date.now() - 365 * DAY_IN_MS);
  const beforeDate = oneYearAgo.toISOString().split('.')[0];
  const posts = await blurtCall('condenser_api.get_discussions_by_author_before_date', [
    BLURT_USER,
    '',
    beforeDate,
    100,
  ]);
  if (posts) {
    const list = [];
    for (const p of posts.reverse()) {
      if (p.permlink && !postedSet.has(p.permlink)) {
        list.push(p.permlink);
      }
    }
    return list;
  }
  return [];
}

async function getPostDetails(permlink) {
  return blurtCall('condenser_api.get_content', [BLURT_USER, permlink]);
}

// সেরি নোডে সরাসরি প্রমাণিত HTTP RPC কল (কনসোলের সফল কল অনুসারে)
async function sendSereyHttpRpc(api, method, params = []) {
  const payload = {
    jsonrpc: '2.0',
    method: 'call',
    params: [api, method, params],
    id: 1,
  };

  const res = await axios.post('https://api.serey.io', payload, {
    headers: {
      'Content-Type': 'application/json',
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    },
    timeout: 20000,
  });

  if (res.data && res.data.error) {
    throw new Error(JSON.stringify(res.data.error));
  }
  return res.data ? res.data.result : null;
}

// সেরি ব্লকচেইনে সরাসরি সাইন ও ব্রডকাস্ট ফাংশন
async function postToSereyNative(title, body, permlink, tags) {
  try {
    console.log('📡 সেরি ব্লকচেইন নোড থেকে বর্তমান ব্লক ডাটা সংগ্রহ করা হচ্ছে...');

    // ১. প্রমাণিত আরপিসি দিয়ে ব্লক ডাটা আনা
    const dgp = await sendSereyHttpRpc('database_api', 'get_dynamic_global_properties', []);
    
    const headBlockNumber = dgp.head_block_number;
    const headBlockId = dgp.head_block_id;

    // TaPoS ব্লকচেইন হিসাব
    const refBlockNum = headBlockNumber & 0xffff;
    const refBlockPrefix = Buffer.from(headBlockId, 'hex').readUInt32LE(4);

    // টাইমস্ট্যাম্প
    const blockTime = new Date(dgp.time + 'Z').getTime();
    const expiration = new Date(blockTime + 60000).toISOString().split('.')[0];

    // ট্যাগ ও মেটাডাটা
    const finalTags = ['news', 'others', 'bengali-community'];
    if (tags && Array.isArray(tags)) {
      tags.forEach(t => {
        const clean = String(t).toLowerCase().replace(/[^a-z0-9\-]/g, '');
        if (clean && !finalTags.includes(clean)) finalTags.push(clean);
      });
    }

    let formattedBody = body;
    if (!formattedBody.includes('<p>') && !formattedBody.includes('<div>')) {
      formattedBody = `<p>${body.replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br/>')}</p>`;
    }

    const jsonMetadata = JSON.stringify({
      tags: finalTags,
      categories: ['news', 'others'],
      community_id: 2,
      community_title: 'Bengali Community',
      type: 1,
      post_to_blockchain: true,
      app: 'serey/0.1',
      format: 'html',
    });

    // ২. অপারেশন অবজেক্ট তৈরি
    const op = [
      'comment',
      {
        parent_author: '',
        parent_permlink: 'news',
        author: SEREY_USER,
        permlink: permlink,
        title: title,
        body: formattedBody,
        json_metadata: jsonMetadata,
      },
    ];

    const tx = {
      ref_block_num: refBlockNum,
      ref_block_prefix: refBlockPrefix,
      expiration: expiration,
      operations: [op],
      extensions: [],
    };

    // ৩. পোস্টিং কি দিয়ে ট্রানজাকশন সাইন করা
    console.log(`🔑 ট্রানজাকশন সাইন করা হচ্ছে...`);
    const signedTx = serey.auth.signTransaction(tx, [SEREY_POSTING_KEY]);

    console.log(`🚀 ব্লকচেইনে সরাসরি ব্রডকাস্ট করা হচ্ছে: ${title}`);

    // ৪. সরাসরি HTTP RPC দিয়ে ব্রডকাস্ট পাঠানো
    try {
      await sendSereyHttpRpc('network_broadcast_api', 'broadcast_transaction_synchronous', [signedTx]);
    } catch (e) {
