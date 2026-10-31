CREATE TABLE products (
    id            SERIAL PRIMARY KEY,
    slug          TEXT         NOT NULL UNIQUE,
    name          TEXT         NOT NULL,
    category      TEXT         NOT NULL,
    description   TEXT         NOT NULL,
    -- Lista de pares [rótulo, valor]: JSONB não preserva a ordem das chaves de objetos.
    specs         JSONB        NOT NULL DEFAULT '[]',
    image         TEXT         NOT NULL,
    price_cents   INTEGER      NOT NULL CHECK (price_cents > 0),
    stock         INTEGER      NOT NULL DEFAULT 0 CHECK (stock >= 0),
    rating        NUMERIC(2,1) NOT NULL DEFAULT 0 CHECK (rating BETWEEN 0 AND 5),
    reviews_count INTEGER      NOT NULL DEFAULT 0
);

CREATE TABLE coupons (
    code         TEXT PRIMARY KEY,
    discount_pct INTEGER NOT NULL CHECK (discount_pct BETWEEN 0 AND 100)
);

CREATE TABLE orders (
    id               SERIAL PRIMARY KEY,
    coupon           TEXT REFERENCES coupons (code),
    payment_method   TEXT        NOT NULL CHECK (payment_method IN ('pix', 'card', 'boleto')),
    subtotal_cents   INTEGER     NOT NULL,
    shipping_cents   INTEGER     NOT NULL,
    discount_cents   INTEGER     NOT NULL,
    total_cents      INTEGER     NOT NULL,
    session_id       TEXT,
    authorization_id TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX orders_created_at_idx ON orders (created_at);

CREATE TABLE order_items (
    order_id         INTEGER NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    product_id       INTEGER NOT NULL REFERENCES products (id),
    quantity         INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents INTEGER NOT NULL,
    PRIMARY KEY (order_id, product_id)
);

-- O id 9 (cabo) fica esgotado; o loadgen usa só os ids 1 a 8.
INSERT INTO products (slug, name, category, description, specs, image, price_cents, stock, rating, reviews_count) VALUES
    ('teclado-mecanico', 'Teclado mecânico 75% em alumínio', 'Teclados',
     'Corpo usinado em alumínio, switches lineares silenciosos lubrificados de fábrica e keycaps PBT. Discreto o bastante para chamadas de vídeo.',
     '[["Layout", "75% (84 teclas)"], ["Switch", "Linear silencioso, 45 gf"], ["Conexão", "USB-C e Bluetooth 5.1"], ["Bateria", "4000 mAh"], ["Peso", "1,6 kg"]]',
     '/static/img/products/teclado-mecanico.svg', 35000, 40, 4.8, 212),
    ('mouse-sem-fio', 'Mouse sem fio ergonômico', 'Mouses',
     'Formato esculpido para a mão direita, scroll eletromagnético e cliques silenciosos. Alterna entre três dispositivos.',
     '[["Sensor", "8000 DPI"], ["Conexão", "Receptor USB-C e Bluetooth"], ["Bateria", "Até 70 dias"], ["Peso", "141 g"]]',
     '/static/img/products/mouse-sem-fio.svg', 12000, 120, 4.6, 348),
    ('monitor-27', 'Monitor 27" QHD', 'Monitores',
     'Painel IPS 2560×1440 com 99% sRGB, bordas finas e base em alumínio com ajuste de altura. Hub USB-C com 65 W de carga.',
     '[["Tela", "27\" IPS, 2560×1440"], ["Taxa de atualização", "75 Hz"], ["Cor", "99% sRGB"], ["Conexões", "USB-C 65 W, HDMI, DisplayPort"]]',
     '/static/img/products/monitor-27.svg', 189900, 3, 4.7, 96),
    ('headset', 'Headset com microfone boom', 'Headsets',
     'Conchas fechadas em espuma memory foam e microfone boom com cancelamento de ruído para reuniões longas.',
     '[["Driver", "40 mm"], ["Microfone", "Boom removível, cardioide"], ["Conexão", "USB-C e P2"], ["Peso", "265 g"]]',
     '/static/img/products/headset.svg', 45000, 60, 4.5, 154),
    ('webcam-full-hd', 'Webcam Full HD', 'Webcams',
     'Lente de vidro com foco automático, correção de luz baixa e tampa de privacidade magnética.',
     '[["Resolução", "1080p a 60 fps"], ["Campo de visão", "90°"], ["Microfone", "Duplo, estéreo"], ["Fixação", "Clipe para monitor e rosca de tripé"]]',
     '/static/img/products/webcam-full-hd.svg', 29900, 80, 4.4, 127),
    ('mousepad-feltro', 'Mousepad de feltro de lã', 'Acessórios',
     'Feltro de lã merino sobre base de cortiça natural. Desliza bem e organiza visualmente a mesa.',
     '[["Dimensões", "90 × 40 cm"], ["Material", "Lã merino e cortiça"], ["Espessura", "4 mm"]]',
     '/static/img/products/mousepad-feltro.svg', 14900, 75, 4.9, 88),
    ('suporte-monitor', 'Suporte articulado de monitor', 'Acessórios',
     'Braço a gás em alumínio com passagem de cabos interna. Libera espaço na mesa e ajusta a altura dos olhos.',
     '[["Compatibilidade", "Monitores de 17\" a 32\""], ["Carga", "2 a 9 kg"], ["Fixação", "Grampo ou ilhós"], ["VESA", "75 × 75 e 100 × 100"]]',
     '/static/img/products/suporte-monitor.svg', 39900, 2, 4.6, 61),
    ('hub-usb-c', 'Hub USB-C 7 em 1', 'Acessórios',
     'Carcaça em alumínio com HDMI 4K, leitor de cartões e carga passante de 100 W.',
     '[["Portas", "HDMI 4K, 3× USB-A, USB-C PD, SD, microSD"], ["Carga passante", "100 W"], ["Cabo", "15 cm"]]',
     '/static/img/products/hub-usb-c.svg', 24900, 45, 4.3, 203),
    ('cabo-usb-c-espiralado', 'Cabo USB-C espiralado', 'Acessórios',
     'Cabo espiralado com conector aviador e malha de nylon, para teclados mecânicos.',
     '[["Comprimento", "1,5 m"], ["Conectores", "USB-C para USB-C, aviador"], ["Revestimento", "Nylon trançado"]]',
     '/static/img/products/cabo-usb-c-espiralado.svg', 9900, 0, 4.7, 42);

INSERT INTO coupons (code, discount_pct) VALUES
    ('DESC10', 10),
    ('GRATIS100', 100);

-- Histórico de 2M pedidos de outras sessões, um item cada. A página de
-- produto consulta "você comprou este produto" por session_id; sem o índice
-- abaixo a consulta vira seq scan em orders (cenário missing_index). As duas
-- tabelas precisam de volume, senão o planner começa pela menor e continua rápido.
INSERT INTO orders (payment_method, subtotal_cents, shipping_cents, discount_cents, total_cents, session_id, created_at)
SELECT 'card', 10000, 0, 0, 10000, md5(n::text), now() - (n % 365) * interval '1 day'
FROM generate_series(1, 2000000) AS n;

-- As FKs são válidas por construção; desligar os triggers de FK só durante a
-- carga derruba o tempo do init de minutos para segundos.
SET session_replication_role = replica;
INSERT INTO order_items (order_id, product_id, quantity, unit_price_cents)
SELECT o.id, p.id, 1, p.price_cents
FROM orders o
JOIN products p ON p.id = 1 + o.id % 8;
RESET session_replication_role;

CREATE INDEX orders_session_id_idx ON orders (session_id);

VACUUM ANALYZE orders;
VACUUM ANALYZE order_items;
