"""Whitespace-folded source anchors, never translations or replacement text.

Evidence: 2026-09-14-cross-buyer-paragraph-ownership-audit.md and its PDF crops.
ZC BN68-25100B p2; AFRICA BN68-25031G p35; ZG BN68-25448A
p8/18/28/38/48; XU BN68-24437C p2. Original fragment text stays untouched.
"""

POWER_SOURCE = {
    ('TK_L02', 'A2', 'TUR'): (
        '• Prizleri, uzatma kablolarını veya adaptörleri voltaj ve kapasitelerinden fazla, aşırı yüklemeyin. Bu, yangın veya elektrik çarpmasına neden olabilir.',
        'Voltaj ve amper bilgileri için kılavuzun güç özellikleri bölümüne veya ürün üzerindeki güç kaynağı etiketine bakın.',
    ),
    ('ZC_L02', 'A2', 'C-FRA'): (
        '• Ne surchargez ni vos prises murales ni vos câbles d’extension ni vos Adaptateur '
        '(tension et puissance installée) Une surcharge pourrait entraîner un incendie ou des décharges électriques.',
        "Reportez-vous à la section portant sur les spécifications électriques du manuel ou à l'étiquette "
        "sur l'alimentation électrique du produit pour connaître les renseignements sur la tension électrique et l'intensité.",
    ),
    ('AFRICA_L05', 'BOOK', 'ARA'): (
        '• لا تقم بتحميل مآخذ الحائط أو أسلاك التمديد أو المحول فوق جهدها وسعتها. فقد يؤدي هذا إلى نشوب حريق أو حدوث صدمة كهربائية.',
        'راجع قسم مواصفات الطاقة في دليل المستخدم أو ملصق مصدر الطاقة الموجود على المنتج للحصول على معلومات عن الجهد وشدة التيار.',
    ),
}

_ENG_FEE = (
    'An administration fee may be charged in the following situations:',
    '(a) An engineer is called out at your request, but it is found that the product has no defect (i.e., where the user manual has not been read).',
    '(b) You bring the unit to the Samsung service centre, but it is found that the product has no defect (i.e., where the user manual has not been read).',
)
FEE_SOURCE = {
    ('TK_L02', 'A2', 'ENG'): _ENG_FEE,
    ('TK_L02', 'A2', 'TUR'): (
        'Aşağıdaki durumlarda bir yönetim ücreti alınabilir:',
        '(a) Talep etmeniz üzerine bir mühendis çağrılır, ancak üründe hiç arıza olmadığı görülürse (yani, kullanıcı kılavuzu okunmadığında).',
        '(b) Üniteyi Samsung servis merkezine götürdüğünüzde, ancak üründe bir arıza olmadığı görülürse (yani, kullanıcı kılavuzu okunmadığında).',
    ),
    ('ZG XN ZT_L05', 'BOOK', 'ENG'): _ENG_FEE,
    ('XU_ENG', 'A3', 'ENG'): _ENG_FEE,
    ('ZG XN ZT_L05', 'BOOK', 'DEU'): (
        'Für Reparaturen an Ihrem Gerät fallen Gebühren an, wenn:',
        '(a) auf Ihren Wunsch ein Techniker zu Ihnen geschickt wird, aber es wird festgestellt, dass kein Defekt des Geräts vorliegt (d. h. wenn das Benutzerhandbuch nicht gelesen wurde).',
        '(b) Sie das Gerät in das Samsung Kundendienstzentrum bringen, aber es wird festgestellt, dass kein Defekt des Geräts vorliegt (d. h. wenn das Benutzerhandbuch nicht gelesen wurde).',
    ),
    ('ZG XN ZT_L05', 'BOOK', 'FRA'): (
        "Des frais d'administration peuvent vous être facturés dans les situations suivantes :",
        "(a) Un technicien intervient à votre demande alors que le produit ne présente aucun défaut (c.-à-d. vous n'avez pas lu le manuel d'utilisation).",
        "(b) Vous apportez le produit dans un centre de service après- vente Samsung alors que le produit ne présente aucun défaut (c.-à-d. vous n'avez pas lu le manuel d'utilisation).",
    ),
    ('ZG XN ZT_L05', 'BOOK', 'ITA'): (
        'Nelle seguenti condizioni è possibile che vengano addebitati costi amministrativi:',
        "(a) l'uscita del tecnico in seguito a una chiamata non porta all'individuazione di alcun difetto nel prodotto (ovvero laddove l'utente non abbia letto il manuale dell'utente).",
        "(b) L'utente ha consegnato l'unità ad un Centro di assistenza Samsung ma non è stato individuato alcun difetto nel prodotto (ovvero laddove l'utente non abbia letto il manuale dell'utente).",
    ),
    ('ZG XN ZT_L05', 'BOOK', 'DUT'): (
        'In de volgende gevallen kunnen administratiekosten in rekening worden gebracht:',
        '(a) Als op uw verzoek een monteur wordt gestuurd, maar het product niet defect is (wanneer u hebt nagelaten de gebruiksaanwijzing te lezen).',
        '(b) Als u het toestel naar het Samsung Servicecenter brengt, maar het product niet defect blijkt (bijv. wanneer u hebt nagelaten de gebruiksaanwijzing te lezen).',
    ),
}
