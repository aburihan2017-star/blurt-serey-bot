const fs = require('fs');
const axios = require('axios');
const WebSocket = require('ws');

// sereyjs প্যাকেজ
let serey;
try {
  serey = require('sereyjs');
} catch (e) {
  serey = require('steem');
}

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

// সেরি নোডে নিরাপদ WebSocket RPC কল
function sendSereyRpc(ws, api, method, params = []) {
  return new Promise((resolve, reject) => {
    const id = Math.floor(Math.random() * 100000);
    const req = {
      id: id,
      method: 'call',
      params: [api, method, params],
    };

    const handler = (data) => {
      try {
        const res = JSON.parse(data.toString());
        if (res.id === id) {
          ws.off('message', handler);
          if (res.error) {
            reject(new Error(JSON.stringify(res.error)));
          } else {
            resolve(res.result);
          }
        }
      } catch (err) {}
    };

    ws.on('message', handler);
    ws.send(JSON.stringify(req));

    setTimeout(() => {
      ws.off('message', handler);
      reject(new Error('RPC Timeout: ' + method));
    }, 15000);
  });
}

// সেরি ব্লকচেইনে সরাসরি সাইন ও ব্রডকাস্ট ফাংশন
function postToSereyNative(title, body, permlink, tags) {
  return new Promise(async (resolve) => {
    const ws = new WebSocket('wss://api.serey.io');

    ws.on('error', (err) => {
      console.error('❌ WebSocket সংযোগ এরর:', err.message);
      resolve(false);
    });

    ws.on('open', async () => {
      try {
        console.log('📡 সেরি ব্লকচেইন নোডের সাথে সরাসরি সংযোগ স্থাপিত হয়েছে!');

        // ১. ডাইনামিক প্রপার্টিজ আনা
        const dgp = await sendSereyRpc(ws, 'database_api', 'get_dynamic_global_properties', []);
        
        const headBlockNumber = dgp.head_block_number;
        const headBlockId = dgp.head_block_id;

        // TaPoS ফিক্স: headBlockId এর সাথে সরাসরি headBlockNumber ম্যাচিং
        const refBlockNum = headBlockNumber & 0xffff;
        const refBlockPrefix = Buffer.from(headBlockId, 'hex').readUInt32LE(4);

        // টাইমস্ট্যাম্প ও এক্সপায়ার্ড টাইম
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

        // ২. কমেন্ট অপারেশন তৈরি
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
        
        // ৪. সরাসরি নোডে ব্রডকাস্ট পাঠানো
        await sendSereyRpc(ws, 'network_broadcast_api', 'broadcast_transaction', [signedTx]);

        console.log(`🎉🎉 পোস্ট সফলভাবে সেরি ব্লকচেইনে লাইভ হয়েছে!`);
        
        // সেরি ওয়েবসাইট ক্যাশ রিফ্রেশ
        try {
          await axios.get(`https://global-api.serey.io/api/v2/serey-web/list-by-author?author=${SEREY_USER}&limit=5&offset=0`, { timeout: 10000 });
        } catch (e) {}

        ws.close();
        resolve(true);
      } catch (err) {
        console.error('❌ ব্রডকাস্ট এরর:', err.message);
        ws.close();
        resolve(false);
      }
    });
  });
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

  let tags = [];
  try {
    const meta = JSON.parse(postInfo.json_metadata || '{}');
    if (meta.tags && Array.isArray(meta.tags)) tags = meta.tags;
  } catch (e) {}

  const cleanTitle = title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  const sereyPermlink = `${cleanTitle.slice(0, 38)}-${Date.now().toString(36)}`;

  console.log(`\nপ্রসেস করা হচ্ছে: ${title}`);
  const success = await postToSereyNative(title, body, sereyPermlink, tags);

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
