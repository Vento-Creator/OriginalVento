"""
UTAG Configuration - System settings and constants
"""
from dataclasses import dataclass
from typing import Dict


@dataclass
class UtagSettings:
    """UTAG system settings"""
    
    # Rate limiting
    max_parallel_utag: int = 5
    default_delay: float = 0.8
    min_delay: float = 0.05
    max_delay: float = 5.0
    
    # Command settings
    max_command_length: int = 15
    max_custom_commands: int = 10
    
    # Timer settings
    timer_check_interval: int = 60  # seconds
    timer_default_interval: int = 3600  # 1 hour
    
    # Game settings
    game_cooldown: int = 300  # 5 minutes
    game_max_per_day: int = 50
    
    # Messages
    messages: Dict[str, str] = None
    
    def __post_init__(self):
        if self.messages is None:
            self.messages = {
                "setup_welcome": "🏷 **UTAG Sozlamalari**\n\nTag komandalarini sozlash.",
                "command_added": "✅ Komanda qo'shildi!",
                "command_removed": "🗑 Komanda o'chirildi!",
                "command_list": "📋 **Tag Komandalari**\n\n{commands}",
                "timer_set": "⏰ Timer sozlandi!",
                "timer_removed": "🗑 Timer o'chirildi!",
                "error_limit": "⚠️ Limit reached!",
                "error_not_found": "❌ Topilmadi!",
                "error": "❌ Xatolik yuz berdi!",
            }


class UtagConstants:
    """UTAG system constants"""
    
    # States
    STATE_IDLE = "idle"
    STATE_SETUP_COMMAND = "setup_command"
    STATE_SETUP_COMMAND_MESSAGE = "setup_message"
    STATE_SETUP_TIMER = "setup_timer"
    STATE_RUNNING = "running"
    
    # Callback data
    CALLBACK_UTAG_START = "utag_start"
    CALLBACK_UTAG_ADD_COMMAND = "utag_add_command"
    CALLBACK_UTAG_REMOVE_COMMAND = "utag_remove_command"
    CALLBACK_UTAG_LIST_COMMANDS = "utag_list_commands"
    CALLBACK_UTAG_SET_TIMER = "utag_set_timer"
    CALLBACK_UTAG_REMOVE_TIMER = "utag_remove_timer"
    CALLBACK_UTAG_CANCEL = "utag_cancel"
    
    # Buttons
    BUTTON_ADD_COMMAND = "➕ Komanda qo'shish"
    BUTTON_REMOVE_COMMAND = "🗑 Komanda o'chirish"
    BUTTON_LIST_COMMANDS = "📋 Komandalar ro'yxati"
    BUTTON_SET_TIMER = "⏰ Timer sozlash"
    BUTTON_REMOVE_TIMER = "🗑 Timer o'chirish"
    BUTTON_CANCEL = "❌ Bekor qilish"
    BUTTON_BACK = "🔙 Orqaga"


# Default tag messages (simplified - can be expanded)
DEFAULT_TAG_MESSAGES = {
    1: "Kibr bo'lmasa bitta kelib keting 👋",
    2: "Yo'qolib ketdingiz, FBI qidiruviga beraylikmi? 🔍",
    3: "Salom do'stim, Tirikmisiz ishqilib? 🗿",
    4: "Qachon kelasiz, choylar sovub, shashliklar kuyib ketdi-ku 🍢",
    5: "Nima gaplar, dunyoda nima yangiliklar bor ekan? 👀",
    6: "Sizsiz guruh xuddi tuzsiz ovqatga o'xshab qoldi 🍲",
    7: "Kelib bir 'a' deb keting, sog'indik 😅",
    8: "Online'da o'tirib javob bermaslik — xiyonat hisoblanadi 💔",
    9: "Ishlar yaxshimi yoki haftalik 'депрессия' damisiz? 🛋",
    10: "Kelib bitta salom berishga tekin premium berishmayaptimi? 😜",
    11: "Sizni deb butun guruh 'wait' rejimida o'tiribdi ⏳",
    12: "Kiring, bu yerda tekin maslahatlar berilyapti 🧠",
    13: "Sizni kutib sochimga oq tushdi-ku brat 🧑‍🦳",
    14: "Telegram'ni faqat mem ko'rish uchun ochasizmi? 🎭",
    15: "Oyda bir ko'rinib, xuddi bayramdek xursand qilasiz-a 🌙",
    16: "Sizni guruhga chaqirish uchun maxsus xat yuboraylikmi? ✉️",
    17: "Bitta 'salom' yozish barmog'ingizni og'ritib qo'ymaydimi? 🙂",
    18: "Keling, chatdagi g'iybatlarni o'tkazib yuborasiz hozir 🤫",
    19: "AFK misiz yoki shunchaki biz bilan gaplashishga 'darajangiz' yetmayaptimi? 🧐",
    20: "Sizsiz davra xuddi Wi-Fi'siz uyga o'xshaydi 📶",
    21: "Internetiz tugab qolmagandir ishqilib? 💸",
    22: "Siz kelmasangiz hozir hammani birma-bir tag qilib chiqaman 😈",
    23: "Guruhga nega kelgansiz? 😑🤔",
    24: "O'zizcha megayulduzsiz-a, chaqirsa ham kelmaydigan ⭐️",
    25: "Kiring, sizga atab maxsus stiker tayyorlab qo'ydik 🎨",
    26: "Javob yozmasangiz kartangizdan 1000 so'm yechib olinadi 💳",
    27: "Sizni ham bitta tag qilib qo'yay, statisika uchun 📊",
    28: "Chatda odam kam, kelib dramani boshlab bering 🍿",
    29: "Qaysi kanallarda aylanib yuribsiz, qayting endi uyingizga 🏠",
    30: "Siz yozmasangiz chatning kayfiyati ko'tarilmayapti 📉",
    31: "Tinchlikmi, yo biror joyga 'prezident' bo'lib saylandingizmi? 🏛",
    32: "Keling, bugun kimni 'g'iybat' qilamiz? 🙈",
    33: "Sizni guruhga tayinlaganimizga ancha bo'ldi, natija qani? 📝",
    34: "Siz yozmaguningizcha ushbu bot ishlamaydi 🤖",
    35: "Iltimos, guruhga kirib bir marta 'yo'talib' qo'ying 🤧",
    36: "Sizni yo'qotib qo'ydik, topganga mukofot bor! 🏆",
    37: "Telefonni qo'lga oling-da, ikki og'iz so'z yozing 📱",
    38: "Ajoyib suhbat ketyapti, faqat siz yetmayapsiz ✨",
    39: "Siz haqingizda xabarlar bor, kelib izoh bering 📰",
    40: "Guruhda jimlik saqlash bo'yicha chempionsiz 🥇",
    41: "Sizni tag qilish biz uchun sharaf, lekin javob bersangiz undan ham yaxshi 🎖",
    42: "Ko'rinib turing, bo'lmasa guruhdan 'pensioner' qilib chiqarib yuboramiz 👴",
    43: "Siz kelmasangiz choyxonaga borilmaydi! ☕️",
    44: "Telegram'ingiz muzlab qolmagan bo'lsa bitta nuqta bo'lsa ham qo'ying ❄️",
    45: "Odam degan ham shunchalik band bo'ladimi? 💼",
    46: "Sizni chaqiraverib botning drayveri kuydi 💥",
    47: "Chatga kirish tekin, bemalol kelib ketishingiz mumkin 🚪",
    48: "Keling, sizsiz hech kim hazillasholmayapti 🤡",
    49: "Birrovga kirib o'ting, 'salom-alik' qilib ketasiz 🤝",
    50: "Bu oxirgi ogohlantirish: Kirmasangiz guruhga maxfiylik kiritiladi ⚠️",
    51: "Seni bezovta qilish bugungi rejam edi. 😂🤝",
    52: "Bir bildirishnoma tashlab ketdim. 🔔😅",
    53: "Kirib ket, yo'qolib qolma. 👀😂",
    54: "Senga omad kulib boqdi. 🍀😎",
    55: "Bugungi mehmon sensan. 🎉😆",
    56: "Tinch o'tirmasang ham mayli. 🤭🤣",
    57: "Seni eslab qo'ydim. 🧠😅",
    58: "Shu yerga kelib iz qoldir. 👣😂",
    59: "Auuuuu👀🤷‍♂️",
    60: "Kel, zerikmaymiz. 😁🎈",
    61: "Senga kichkina ish chiqdi. 📩😏",
    62: "Bildirishnoma bekorga kelmaydi. 🔔🤨",
    63: "Telefoning bekor yotmasin. 📱😂",
    64: "Shu yerga bir nazar tashla. 👁️😉",
    65: "Seni qidirayotganlar bor emish. 🕵️😂",
    66: "Bugun navbat senga. 🎯😄",
    67: "Kirib kulib ket. 😂✨",
    68: "Yo'qolgan odam topildi. 🔍🤣",
    69: "Ko'rmasang afsus bo'ladi. 😬👀",
    70: "Men bo'lsam kirardim. 😎🤝",
    71: "Bir marta bosib kir. ☝️😂",
    72: "Vaqtingni 5 soniya olaman. ⏳😅",
    73: "Sabr qil, qiziq joyi oldinda. 😏🍿",
    74: "Endi sen ham ko'r. 👀🔥",
    75: "Bildirishnoma seni kutayotgandi. 🔔😁",
    76: "Telefoning zerikmasin. 📱🤣",
    77: "Tasodifan seni bosdim. 😅👉",
    78: "Shu post sendan yashirin emas. 👁️😎",
    79: "Kelib jim turishing ham mumkin. 🤫😂",
    80: "Faqat o'qib ketma. 📖😏",
    81: "Bir kulib ket. 😂🌸",
    82: "Buni o'tkazma. 🚫👀",
    83: "Shu yerga adashib kel. 🧭🤣",
    84: "Adashsang ham shu yerga kel. 😅📍",
    85: "Endi bahona yo'q. 🙃🚪",
    86: "Kirganing bilinmaydi. 🥷😂",
    87: "Chaqiruv qabul qilindimi? 📞😄",
    88: "Shu yerdan o'tib ketma. 🚶👀",
    89: "Seni internet chaqiryapti. 🌐🤣",
    90: "Bir qarasang o'lmaysan. 👀😂",
    91: "Bugun omadli odamsan. 🍀😎",
    92: "Yana seni topdim. 🔍😁",
    93: "Shu safar qochma. 🏃😂",
    94: "Telefoningni uyg'otdim. 📱⏰",
    95: "Bitta signal tashladim. 📡😅",
    96: "Kirib salom ber. 👋😄",
    97: "Shu yerda yig'ilish. 🪑😂",
    98: "Jim o'tirma. 🤐😆",
    99: "Sen kerak bo'lib qolding. 🫵😎",
    100: "Seni sinab ko'rdim. 🧪😂",
    101: "Bildirishnomang ko'payaversin. 🔔🤣",
    102: "Bugun mashhursan. 🌟😎",
    103: "O'zingni ko'rsat. 👀✨",
    104: "Bir marta javob ber. 💬😅",
    105: "Kutilmagan mehmon. 🚪😂",
    106: "Internet seni sog'indi. 🌍🥹",
    107: "Qaytib kel. 🔙😁",
    108: "Biror narsa yozib ket. ✍️😂",
    109: "Shu yerga mos odamsan. 😎📍",
    110: "O'zingni yashirma. 🙈🤣",
    111: "Bitta kulgi tashlab ket. 😂🎭",
    112: "Men seni topdim. 🕵️😄",
    113: "Endi navbat seniki. 🎯😉",
    114: "Bekor yurmagandirsan. 🚶😅",
    115: "Ko'rib o'tsang bo'ladi. 👀🤝",
    116: "Hali ham shu yerdaman. 😌📍",
    117: "Bildirishnomani bekor yubormadim. 🔔😏",
    118: "O'qimasang ham kir. 📖😂",
    119: "Sen uchun maxsus. 🎁😎",
    120: "Bugun tanlov sensan. 🏆🤣",
    121: "Telefoning jiringlamasa ham keldim. 📱😂",
    122: "Tinchlikni buzdim. 🤭💥",
    123: "Shu yerda uchrashamiz. 🤝📍",
    124: "Adashib kirmagin, ataylab kir. 😅🚪",
    125: "Men seni tanladim. 🫵😎",
    126: "Bugungi omad egasi. 🍀👑",
    127: "Bir soniya yetadi. ⏱️😁",
    128: "Zeriksang shu yerga kel. 😴😂",
    129: "Kulgiga sabab topildi. 😂🎉",
    130: "Kutilmagan burilish. 🔄😲",
    131: "Internet guvoh. 🌐🤣",
    132: "Shu post seni kutyapti. 📩👀",
    133: "Men chaqirdim, kel. 📣😄",
    134: "Bitta imkon berdim. 🎁😉",
    135: "Bugun mashhur bo'libsan. 🌟😂",
    136: "Shu safar javob yoz. 💬😏",
    137: "Bildirishnoma bekorga emas. 🔔🤭",
    138: "Telefoningni band qildim. 📱🤣",
    139: "Ko'rib indama. 👀🤫",
    140: "Shu yerga qo'n. 🕊️😂",
    141: "Bitta qarab ketgin. 👁️😄",
    142: "Yo'qolib ketma. 🚶😅",
    143: "Kel, gap ko'p emas. 🤝😁",
    144: "Sir emas, seni chaqirdim. 🤫😂",
    145: "Shunchaki bezovta qildim. 😜📩",
    146: "O'qib kulishing mumkin. 📖🤣",
    147: "Bugungi vazifa shu. 📋😎",
    148: "Oxirigacha qarab chiq. 👀🔥",
    149: "Men vazifamni bajardim. ✅😂",
    150: "Endi navbat senga. 🫵😄",
    151: "Qaysi tarafga qarab yuguryapmiz 🏃‍♂️💨",
    152: "Guruhda jimjitlik, kimdir uzr so'rasin 🤐🗿",
    153: "sz bn bitta profil ochaylik kelin 🙈✨",
    154: "E, sz hali ham uxlab yurbszmi 🥱💤",
    155: "Profilizga kirdim, rasmlariz daxshatku 😎🔥",
    156: "Shu grda faqat sz normalniy gapirasiz 🤩👌",
    157: "Bitta spam bosvorilar, asabga tegyapdi 😤❌",
    158: "qachon ovqatga chaqirasiz endi 🍕🤤",
    159: "Szni qayerdadir ko'rganman exact 🧐🔍",
    160: "Bugun kimdur yutadi, lekin sz emas 😀💸",
    161: "Mafiyada shuncha odam ichida meni o'ldirdingizmi 🤦‍♂️🗡",
    162: "Katta xolamni kelini bo'lasizmi 👰‍♀️✨",
    163: "sz bn bitta kofe ichiylik ☕️🥹",
    164: "Gapirib turing, uyqu kelyapdi 😴🥱",
    165: "Voy, guruhga kim kirib keldi 👀🤩",
    166: "Yozing, szni kutyapmiz o bez 🤨⚡️",
    167: "Szni profilizni kimdir kuzatvotti 👁️🗨️🫣",
    168: "Botdan 100 ta almaz yutib oldim 💎🤩",
    169: "Bitta reaksiya bosish shunchalik qiyinmi 🤨🔥",
    170: "Nimadir deymoqchidim, esdan chiqdi 🤦‍♂️🗿",
    171: "Boylikmi yoki szmi 😄💎",
    172: "qarzizni qachon yopasiz aka 💸🙄",
    173: "szni ovozli xabarizi eshitdim daxshat 🎧🤩",
    174: "Guruhni admindanu szni aytdi 🤫🏼",
    175: "Bitta \"Salom\" deyish shunchalik qiyinmi 🥹✨",
    176: "Nega hammani block qvosz 🚫🫥",
    177: "Kimdir uylanish haqida o'ylayapti 👰‍♂️🤵‍♀️",
    178: "sz bn parra bo'lish daxshat ekan 🤩💥",
    179: "Bugun o'yinda hamma yutqazdi, szdan tashqari 😎🏆",
    180: "Nikizni kim qo'yib bergan o'zi 🤨🏷",
    181: "Yozishni bilmasangiz, qaramang 🗿🙈",
    182: "Kecha tushimda szni ko'rdim 🥱💫",
    183: "Admin aka shu bolani ban qiling 🔨😤",
    184: "Teliz zaryadi tugayapti, zaryadga qo'ying 🔋👀",
    185: "Keling bir razbor qilamz😂🤺",
    186: "Otangizni ismi nima edi 🧐🎩",
    187: "Sizni ko'rib yuragim to'xtab qoldi 🫀💥",
    188: "Qanday kinolar yoqadi szga 🍿🎥",
    189: "Guruhda bitta sz yetmay turuvdingiz 🌟🤩",
    190: "Qo'lingizdagi soatni qayerdan olgansiz ⌚️🤔",
    191: "Bitta choyxona bor ekanda endi 🍵🤤",
    192: "Nega muncha jiddiysiz 🗿😒",
    193: "sz bn duat qilamizmi TikTokda 📲🤪",
    194: "Don kelyapdi, qochilar 🕵️‍♂️💥",
    195: "szni sochlaringizga gap yo'q 💇‍♀️✨",
    196: "Nima bu, yozganlarizni tushunib bo'lmayapti 🤦‍♂️🌀",
    197: "Shu grda faqat sz bn gaplashgim kelyapdi 🥹❤️",
    198: "Mashinangizni markasi nima 🏎💨",
    199: "Ismingizni ikkinchi harfi 'A' ekanu 🧐✨",
    200: "Ko'zingizga achishmadi devatishibdi 👁👄",
    201: "sz bn parkga boraylik 🍦🎈",
    202: "Kechqurun o'yin bor, o'tmasez ban 😂🎮",
    203: "Biz tomonda qor yo'g'yapti, sizdachi ❄️🥶",
    204: "Sevganiz szni tashlab ketdimi 🥺💔",
    205: "sz bn gaplashsak, vaqt qanday o'tgani bilinmaydi ⏰✨",
    206: "Komisar sizni qidiryapti 🕵️‍♂️🚨",
    207: "Bitta stiker tashlang, kayfiyat ko'tarilsin 🎭😆",
    208: "Kotta bolalar yozmaydi, jim o'tiradi 🗿🚬",
    209: "Nechta akangiz bor 🤔👊",
    210: "sz bn rasmg tushaylik 📸🤩",
    211: "Bugungi kuniz daxshat o'tdimi 🌟🥳",
    212: "szni ko'rib hamma jim bo'lib qoldi 🫥👀",
    213: "Telegramizni kim ochib bergan 📲🤐",
    214: "Yana bir marta yozsangiz, sevib qolaman ❤️🔥🤪",
    215: "szni kulishingiz qaysidir aktrisaga o'xshaydi 🎬✨",
    216: "Sovchilarimiz qachon boradi 💐👰‍♀️",
    217: "Telefoningiz iPhone-mi yoki Samsung 📱🤔",
    218: "sz bn bitta rasm tushsak, Instagram portlaydi 📸💥",
    219: "Onlaynsiz, lekin yozmayapsiz 🙄💔",
    220: "Voy, muncha chiroyli so'zlar yozasiz 🥹💬",
    221: "Bitta golosovoy yuboring, eshitaylik 🎧🎶",
    222: "szni kayfiyatingiz yo'qmi bugun 😕☁️",
    223: "Guruhdagi eng aqlli odam kim bilasizmi 🧐🧠",
    224: "Szni orqangizdan gapirishyapti 🤫👀",
    225: "Qandaysiz endi, ahvollar joyidami 😀✌️",
    226: "Yozing, yo'qsa guruhdan chiqib ketaman 😤🚪",
    227: "sz bn bitta kinoga boraylik 🍿🎟",
    228: "Kechasi soat 3 da nima qilyabdingiz online 🧐🌙",
    229: "szni profilizga necha kishi kirdi bugun 📊👀",
    230: "Sovuqda qalinroq kiyining 🧥🥶",
    231: "Bitta prikol ayting, kulaylik 😆🎭",
    232: "szni ovozingiz daxshat ekanu 🎙🤩",
    233: "Nimaga muncha ozib ketdingiz 😳🥗",
    234: "sz bn bitta Telegram kanal ochaylik 📢✨",
    235: "Bugun necha kishini aldadingiz 🙈🤥",
    236: "Guruhda eng ko'p gapiradigan odam szsiz 🗣💥",
    237: "Qaysi viloyatdansiz o'zi 🗺️🧐",
    238: "szni tabassumingiz sehrli ekan ✨🥹",
    239: "Bitta muzqaymoq olib bering 🍦🥺",
    240: "Nimaga menga yozmayapsiz 🙄💔",
    241: "sz bn uyin o'ynash daxshat ekan 🎮🥳",
    242: "Aka, moshinangizni kalitini berib turing 🔑🏎",
    243: "Tushimda szni ko'rdim, uyg'onib ketdim 😴💥",
    244: "Guruh admini szni maqtadi 👏🤩",
    245: "Bitta savol bersam, to'g'risini aytasizmi 🧐💬",
    246: "szni ko'nglingiz juda nozikda 🌸🥺",
    247: "Bugun kimning tug'ilgan kuni 🎂🥳",
    248: "sz bn gaplashsak, dunyo to'xtab qoladi 🌍✨",
    249: "Bo'ldi, sz guruhni yulduzisiz 🌟😎"
}


# Default settings instance
default_settings = UtagSettings()