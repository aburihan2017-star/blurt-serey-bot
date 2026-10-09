// ১. WebSocket লেভেলে { } কে [ ] বানানোর গ্লোবাল ইন্টারসেপ্টর (C++ Assert Fix)
const WebSocket = require('ws');
const origSend = WebSocket.prototype.send;
WebSocket.prototype.send = function (data, ...args) {
  if (typeof data === 'string') {
    try {
      const parsed = JSON.parse(data);
      if (
        parsed.method === 'call' &&
        Array.isArray(parsed.params) &&
        parsed.params.length >= 3 &&
        typeof parsed.params[2] === 'object' &&
        !Array.isArray(parsed.params[2]) &&
        Object.keys(parsed.params[2]).length === 0
      ) {
        parsed.params[2] = [];
        data = JSON.stringify(parsed);
      }
    } catch (e) {
      data = data.replace(
        '["database_api","get_dynamic_global_properties",{}]',
        '["database_api","get_dynamic_global_properties",[]]'
      );
    }
  }
  return origSend.call(this, data, ...args);
};

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

// সেরি অফিসিয়াল নেটওয়ার্ক কনফিগারেশন
serey.api.setOptions({ url: 'wss://api.serey.io' });
serey.config.set('address_prefix', 'SRY');
serey.config.set('chain_id', '5205c25d3e87cb3e8e527e6fbbf324b7b2b9fe7a7192c604ce5b174d08987324');

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

function broadcastToSerey(title, body, permlink, tags) {
  return new Promise((resolve) => {
    const parentAuthor = '';
    const parentPermlink = 'news';

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

    console.log(`🚀 সেরি ব্লকচেইনে সরাসরি ব্রডকাস্ট করা হচ্ছে: ${title}`);
    console.log(`📌 পারমালিঙ্ক: ${permlink}`);

    serey.broadcast.comment(
      SEREY_POSTING_KEY,
      parentAuthor,
      parentPermlink,
      SEREY_USER,
      permlink,
      title,
      formattedBody,
      jsonMetadata,
      async (err, result) => {
        if (err) {
          console.error(`❌ ব্রডকাস্ট এরর:`, err.message || err);
          resolve(false);
        } else {
          console.log(`🎉🎉 পোস্ট সফলভাবে সেরি ব্লকচেইনে লাইভ হয়েছে! TxID:`, result?.id || 'Success');
          try {
            await axios.get(`https://global-api.serey.io/api/v2/serey-web/list-by-author?author=${SEREY_USER}&limit=5&offset=0`, { timeout: 10000 });
          } catch (e) {}
          resolve(true);
        }
      }
    );
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
  const success = await broadcastToSerey(title, body, sereyPermlink, tags);

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
