const fs = require('fs');
const axios = require('axios');
const serey = require('sereyjs');

// কনফিগারেশন
const BLURT_USER = 'aburihan1';
const SEREY_USER = process.env.SEREY_USERNAME || 'raihan123';
const SEREY_POSTING_KEY = (process.env.SEREY_POSTING_KEY || '').trim();

const DATA_FILE = 'automation_data.json';
const MAX_DAILY_POSTS = 2;
const DAY_IN_MS = 86400 * 1000;

const SEREY_CHAIN_ID = '5205c25d3e87cb3e8e527e6fbbf324b7b2b9fe7a7192c604ce5b174d08987324';
const SEREY_PREFIX = 'SRY';

// সেরি চেইন কনফিগ সেট
serey.config.set('address_prefix', SEREY_PREFIX);
serey.config.set('chain_id', SEREY_CHAIN_ID);

const BASE_HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
  'Accept': 'application/json, text/plain, */*',
  'Content-Type': 'application/json',
  'Referer': 'https://bengali.serey.io/write/new',
  'Origin': 'https://bengali.serey.io',
};

const BLURT_NODES = [
  'https://rpc.blurt.blog',
  'https://rpc.beblurt.com',
  'https://blurtrpc.dagobert.uk',
];

async function blurtCall(method, params) {
  const payload = { jsonrpc: '2.0', method, params, id: 1 };
  for (const node of BLURT_NODES) {
    try {
      const res = await axios.post(node, payload, { timeout: 8000 });
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

// সেরি ওয়েব লগইন টোকেন আনা
async function getSereyToken() {
  try {
    const loginUrl = 'https://global-api.serey.io/api/v2/auth/login';
    const payload = { username: SEREY_USER, password: SEREY_POSTING_KEY };
    const r = await axios.post(loginUrl, payload, { headers: BASE_HEADERS, timeout: 20000 });
    const data = r.data;
    return data.token || data.accessToken || data.data?.token || data.data?.accessToken;
  } catch (err) {
    return null;
  }
}

// সেরি ব্লকচেইন নোডে প্রমাণিত HTTP RPC কল
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
      'User-Agent': BASE_HEADERS['User-Agent'],
    },
    timeout: 20000,
  });

  if (res.data && res.data.error) {
    throw new Error(JSON.stringify(res.data.error));
  }
  return res.data ? res.data.result : null;
}

// সেরি ব্লকচেইন ও ওয়েব ডাটাবেজে একই সাথে পোস্ট সম্পন্ন করা (ব্রাউজারের মতো অবিকল)
async function postDualSerey(title, body, permlink) {
  try {
    // ধাপ ১: ব্লকচেইনে সাইন ও ব্রডকাস্ট
    console.log('📡 সেরি ব্লকচেইন নোড থেকে বর্তমান ব্লক ডাটা সংগ্রহ করা হচ্ছে...');
    const dgp = await sendSereyHttpRpc('database_api', 'get_dynamic_global_properties', []);
    
    const headBlockNumber = dgp.head_block_number;
    const headBlockId = dgp.head_block_id;
    const refBlockNum = headBlockNumber & 0xffff;
    const refBlockPrefix = Buffer.from(headBlockId, 'hex').readUInt32LE(4);
    const blockTime = new Date(dgp.time + 'Z').getTime();
    const expiration = new Date(blockTime + 60000).toISOString().split('.')[0];

    let formattedBody = body;
    if (!formattedBody.includes('<p>') && !formattedBody.includes('<div>')) {
      formattedBody = `<p>${body.replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br/>')}</p>`;
    }

    const op = [
      'comment',
      {
        parent_author: '',
        parent_permlink: 'bengali-community',
        author: SEREY_USER,
        permlink: permlink,
        title: title,
        body: formattedBody,
        json_metadata: '',
      },
    ];

    const tx = {
      ref_block_num: refBlockNum,
      ref_block_prefix: refBlockPrefix,
      expiration: expiration,
      operations: [op],
      extensions: [],
    };

    console.log(`🔑 আসল অনুমোদিত পোস্টিং কি দিয়ে ট্রানজাকশন সাইন করা হচ্ছে...`);
    const signedTx = serey.auth.signTransaction(tx, [SEREY_POSTING_KEY]);

    console.log(`🚀 ১. সেরি ব্লকচেইনে সরাসরি ব্রডকাস্ট করা হচ্ছে: ${title}`);
    await sendSereyHttpRpc('network_broadcast_api', 'broadcast_transaction_synchronous', [signedTx]);
    console.log(`🎉🎉 পোস্ট সরাসরি ব্লকচেইনে সফলভাবে রেকর্ড হয়েছে!`);

    // ধাপ ২: সেরি ওয়েব ডাটাবেজে (MongoDB) রেজিস্টার করা (ব্রাউজারের h.lF ফাংশন অনুযায়ী)
    console.log(`📝 ২. সেরি ওয়েব ডাটাবেজে পোস্ট রেজিস্টার করা হচ্ছে...`);
    const token = await getSereyToken();
    if (token) {
      const headers = { ...BASE_HEADERS, Authorization: `Bearer ${token}` };
      const webPayload = {
        title: title,
        desc: formattedBody,
        body: formattedBody,
        permlink: permlink,
        community_id: 2,
        community_title: 'Bengali Community',
        post_to_blockchain: true,
        tags: ['news', 'others', 'bengali-community'],
        type: 1,
        posts: [
          {
            title: title,
            desc: formattedBody,
            body: formattedBody,
            posts: formattedBody,
            permlink: permlink,
            tags: ['news', 'others', 'bengali-community'],
            categories: 'news',
            community: 'Bengali Community',
            community_id: 2,
            post_to_blockchain: true,
          }
        ],
      };

      try {
        await axios.post('https://global-api.serey.io/api/v2/draft-post/create-or-update', webPayload, { headers, timeout: 20000 });
        console.log(`✅ সেরি ওয়েব ডাটাবেজে পোস্ট সফলভাবে সিঙ্ক হয়েছে!`);
      } catch (dbErr) {
        console.log('ডাটাবেজ সিঙ্ক নোটিশ:', dbErr.message);
      }
    }

    // ওয়েবসাইট ক্যাশ রিফ্রেশ
    try {
      await axios.get(`https://global-api.serey.io/api/v2/serey-web/list-by-author?author=${SEREY_USER}&limit=5&offset=0`, { timeout: 10000 });
    } catch (e) {}

    return true;
  } catch (err) {
    console.error(`❌ ব্রডকাস্ট এরর:`, err.message);
    return false;
  }
}

async function main() {
  console.log('বট চালু হচ্ছে...');
  if (!SEREY_POSTING_KEY) {
    console.error('ত্রুটি: SEREY_POSTING_KEY পাওয়া যায়নি!');
    return;
  }

  const data = loadData();
  const now = Date.now();

  data.timestamps = (data.timestamps || []).filter(t => now - t < DAY_IN_MS);
  if (data.timestamps.length >= MAX_DAILY_POSTS) {
    console.log(`আজকের দৈনিক সীমা (${MAX_DAILY_POSTS} টি পোস্ট) পূর্ণ হয়েছে।`);
    return;
  }

  const postedSet = new Set(data.posted || []);

  if (!data.queue || data.queue.length === 0) {
    console.log('ব্লার্ট থেকে ১ বছর আগের পোস্ট আনা হচ্ছে...');
    const fetched = await fetchOneYearOldPosts(postedSet);
    data.queue = fetched;
    saveData(data);
  }

  if (!data.queue || data.queue.length === 0) {
    console.log('পোস্ট করার মতো কোনো নতুন পোস্ট পাওয়া যায়নি।');
    return;
  }

  const permlinkToPost = data.queue.shift();
  const postInfo = await getPostDetails(permlinkToPost);

  if (!postInfo || !postInfo.title) {
    console.log(`পোস্ট ডাটা পাওয়া যায়নি, স্কিপ: ${permlinkToPost}`);
    data.posted = data.posted || [];
    data.posted.push(permlinkToPost);
    saveData(data);
    return;
  }

  const title = postInfo.title;
  const body = postInfo.body;

  // পরিষ্কার ইউনিক পারমালিঙ্ক তৈরি
  const cleanTitle = title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  const sereyPermlink = `${cleanTitle.slice(0, 38)}-${Date.now().toString(36)}`;

  console.log(`\nপ্রসেস করা হচ্ছে: ${title}`);
  const success = await postDualSerey(title, body, sereyPermlink);

  if (success) {
    data.posted = data.posted || [];
    data.posted.push(permlinkToPost);
    data.timestamps = data.timestamps || [];
    data.timestamps.push(now);
    console.log('ডাটা সেভ করা হয়েছে।');
  } else {
    data.queue.push(permlinkToPost);
  }

  saveData(data);
  console.log('\nপ্রক্রিয়া সম্পূর্ণ হয়েছে।');
}

main();
