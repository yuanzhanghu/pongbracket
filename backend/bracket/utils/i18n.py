"""Runtime localisation of user-facing backend messages.

The Chinese source string doubles as the message id (gettext style), so `zh` — the
default — needs no catalog entry and behaves exactly as before this module existed.
A missing translation degrades to the Chinese source instead of raising.

The lookup function is called ``tr`` rather than the conventional ``_``: route
handlers use ``_`` and ``__`` as names for unused ``Depends(...)`` parameters, which
would shadow a module-level ``_`` inside exactly the functions that need it.

Stdlib only — this module is imported from routes, sql and logic alike.
"""

from contextvars import ContextVar

DEFAULT_LANGUAGE = "zh"
SUPPORTED_LANGUAGES = ("zh", "en", "fr")

_active_language: ContextVar[str] = ContextVar("active_language", default=DEFAULT_LANGUAGE)
_individual_wording: ContextVar[bool] = ContextVar("individual_wording", default=False)


def set_language(language: str) -> None:
    """Set the language for the current request. Unknown languages fall back to `zh`."""
    _active_language.set(language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE)


def get_language() -> str:
    return _active_language.get()


def set_individual_wording(individual: bool) -> None:
    """Say whether the current request is about an individual tournament.

    A "team" is a single person there, so the messages listed in `INDIVIDUAL_MESSAGES`
    talk about 参赛人员 (participants) instead of 队伍 (teams).
    """
    _individual_wording.set(individual)


def get_individual_wording() -> bool:
    return _individual_wording.get()


def parse_accept_language(header: str | None) -> str:
    """Pick the best supported language from an `Accept-Language` header.

    Only the base language is matched (`en-US` -> `en`) and entries are ranked by their
    q-value, highest first, ties broken by the order they appear in. Falls back to `zh`.
    """
    if not header:
        return DEFAULT_LANGUAGE

    candidates: list[tuple[float, int, str]] = []
    for index, entry in enumerate(header.split(",")):
        tag, _semicolon, parameters = entry.strip().partition(";")
        base_language = tag.strip().split("-")[0].lower()
        if base_language not in SUPPORTED_LANGUAGES:
            continue

        quality = 1.0
        for parameter in parameters.split(";"):
            key, equals, value = parameter.partition("=")
            if equals and key.strip().lower() == "q":
                try:
                    quality = float(value.strip())
                except ValueError:
                    quality = 0.0

        if quality > 0:
            candidates.append((-quality, index, base_language))

    if not candidates:
        return DEFAULT_LANGUAGE

    return min(candidates)[2]


# Message id (the Chinese source string) -> {language: translation}.
TRANSLATIONS: dict[str, dict[str, str]] = {
    # --- Unique index violations (bracket/utils/errors.py) ---
    "该仪表板链接已被占用": {
        "en": "This dashboard link is already taken",
        "fr": "Ce lien de tableau de bord est déjà pris",
    },
    "该邮箱已被使用": {
        "en": "This email address is already in use",
        "fr": "Cette adresse e-mail est déjà utilisée",
    },
    "该队伍已被分配到其他阶段项目": {
        "en": "This team is already assigned to another stage item",
        "fr": "Cette équipe est déjà affectée à un autre élément d'étape",
    },
    "该参赛人员已被分配到其他阶段项目": {
        "en": "This participant is already assigned to another stage item",
        "fr": "Ce participant est déjà affecté à un autre élément d'étape",
    },
    "该晋级位已被分配到其他阶段项目": {
        "en": "This qualifying place is already assigned to another stage item",
        "fr": "Cette place qualificative est déjà affectée à un autre élément d'étape",
    },
    "已存在相同标识的积分类别": {
        "en": "A rating category with this key already exists",
        "fr": "Une catégorie de classement avec cette clé existe déjà",
    },
    "该账号在此积分类别中已有积分": {
        "en": "This account already has a rating in this category",
        "fr": "Ce compte possède déjà un classement dans cette catégorie",
    },
    "该队伍已绑定其他账号": {
        "en": "This team is already linked to another account",
        "fr": "Cette équipe est déjà liée à un autre compte",
    },
    "该参赛人员已绑定其他账号": {
        "en": "This participant is already linked to another account",
        "fr": "Ce participant est déjà lié à un autre compte",
    },
    "该账号在本比赛中已有队伍": {
        "en": "This account already has a team in this tournament",
        "fr": "Ce compte a déjà une équipe dans ce tournoi",
    },
    "该账号已是本比赛的记分员": {
        "en": "This account is already a scorer for this tournament",
        "fr": "Ce compte est déjà marqueur de ce tournoi",
    },
    "该成员已在你的信任列表中": {
        "en": "This member is already on your trusted list",
        "fr": "Ce membre figure déjà dans votre liste de confiance",
    },
    "你已关注该比赛": {
        "en": "You already follow this tournament",
        "fr": "Vous suivez déjà ce tournoi",
    },
    # --- Foreign key violations (bracket/utils/errors.py) ---
    "该比赛还有场地，请先删除场地": {
        "en": "This tournament still has courts, delete them first",
        "fr": "Ce tournoi comporte encore des terrains, supprimez-les d'abord",
    },
    "该队伍仍关联着比赛对阵": {
        "en": "This team is still linked to matches in the tournament",
        "fr": "Cette équipe est encore liée à des matchs du tournoi",
    },
    "该参赛人员仍关联着比赛对阵": {
        "en": "This participant is still linked to matches in the tournament",
        "fr": "Ce participant est encore lié à des matchs du tournoi",
    },
    "该队伍不能作为此阶段项目的输入": {
        "en": "This team cannot be used as an input of this stage item",
        "fr": "Cette équipe ne peut pas servir d'entrée à cet élément d'étape",
    },
    "该参赛人员不能作为此阶段项目的输入": {
        "en": "This participant cannot be used as an input of this stage item",
        "fr": "Ce participant ne peut pas servir d'entrée à cet élément d'étape",
    },
    "该比赛还有阶段，请先删除阶段": {
        "en": "This tournament still has stages, delete them first",
        "fr": "Ce tournoi comporte encore des étapes, supprimez-les d'abord",
    },
    "该比赛还有队伍，请先删除队伍": {
        "en": "This tournament still has teams, delete them first",
        "fr": "Ce tournoi comporte encore des équipes, supprimez-les d'abord",
    },
    "该比赛还有参赛人员，请先删除参赛人员": {
        "en": "This tournament still has participants, delete them first",
        "fr": "Ce tournoi comporte encore des participants, supprimez-les d'abord",
    },
    "该俱乐部下还有比赛，请先删除比赛": {
        "en": "This club still has tournaments, delete them first",
        "fr": "Ce club comporte encore des tournois, supprimez-les d'abord",
    },
    "该比赛还有排名设置，请先删除排名": {
        "en": "This tournament still has ranking settings, delete them first",
        "fr": "Ce tournoi comporte encore des barèmes de classement, supprimez-les d'abord",
    },
    # --- Authentication and permissions ---
    "登录状态无效，请重新登录": {
        "en": "Your session is no longer valid, please sign in again",
        "fr": "Votre session n'est plus valide, veuillez vous reconnecter",
    },
    "登录状态无效，或该页面未公开": {
        "en": "Your session is no longer valid, or this page is not public",
        "fr": "Votre session n'est plus valide, ou cette page n'est pas publique",
    },
    "该操作需要站点管理员权限": {
        "en": "This action requires site administrator privileges",
        "fr": "Cette action requiert des droits d'administrateur du site",
    },
    "你没有权限为本比赛录入比分": {
        "en": "You are not allowed to record scores for this tournament",
        "fr": "Vous n'êtes pas autorisé à saisir les scores de ce tournoi",
    },
    "邮箱/名称或密码错误": {
        "en": "Incorrect email/username or password",
        "fr": "Adresse e-mail/nom d'utilisateur ou mot de passe incorrect",
    },
    "你没有权限访问该比赛": {
        "en": "You are not allowed to access this tournament",
        "fr": "Vous n'êtes pas autorisé à accéder à ce tournoi",
    },
    # --- Users ---
    "无权查看该用户信息": {
        "en": "You are not allowed to view this user's details",
        "fr": "Vous n'êtes pas autorisé à consulter les informations de cet utilisateur",
    },
    "无权修改该用户信息": {
        "en": "You are not allowed to change this user's details",
        "fr": "Vous n'êtes pas autorisé à modifier les informations de cet utilisateur",
    },
    "该名称已被使用": {
        "en": "This name is already taken",
        "fr": "Ce nom est déjà pris",
    },
    "名称不能为空": {
        "en": "The name cannot be empty",
        "fr": "Le nom ne peut pas être vide",
    },
    "名称不能包含 @ 字符": {
        "en": "The name cannot contain the “@” character",
        "fr": "Le nom ne peut pas contenir le caractère « @ »",
    },
    "当前暂不开放注册": {
        "en": "Registration is currently closed",
        "fr": "Les inscriptions sont actuellement fermées",
    },
    "当前暂不开放演示账户": {
        "en": "Demo accounts are currently unavailable",
        "fr": "Les comptes de démonstration sont actuellement indisponibles",
    },
    "人机验证失败": {
        "en": "Captcha verification failed",
        "fr": "Échec de la vérification anti-robot",
    },
    # --- Tournaments ---
    "找不到该比赛": {
        "en": "Tournament not found",
        "fr": "Tournoi introuvable",
    },
    "比赛名“{name}”已存在": {
        "en": "A tournament named “{name}” already exists",
        "fr": "Un tournoi nommé « {name} » existe déjà",
    },
    "比赛已处于该状态": {
        "en": "The tournament is already in that state",
        "fr": "Le tournoi est déjà dans cet état",
    },
    "俱乐部 ID 无效": {
        "en": "Invalid club ID",
        "fr": "Identifiant de club invalide",
    },
    "只有个人赛可以参与积分": {
        "en": "Only individual tournaments can count towards a rating",
        "fr": "Seuls les tournois individuels peuvent compter pour un classement",
    },
    "已归档的比赛不能修改": {
        "en": "An archived tournament cannot be changed",
        "fr": "Un tournoi archivé ne peut pas être modifié",
    },
    "赛事已结算；请先撤销结算再删除或修改": {
        "en": "The tournament is settled, undo the settlement before deleting or changing it",
        "fr": "Le tournoi est réglé, annulez le règlement avant de le supprimer ou de le modifier",
    },
    "无法关注你无权查看的比赛": {
        "en": "You cannot follow a tournament you are not allowed to view",
        "fr": "Vous ne pouvez pas suivre un tournoi que vous n'êtes pas autorisé à consulter",
    },
    # --- Teams ---
    "队伍名“{name}”已存在": {
        "en": "A team named “{name}” already exists",
        "fr": "Une équipe nommée « {name} » existe déjà",
    },
    "参赛人员“{name}”已存在": {
        "en": "A participant named “{name}” already exists",
        "fr": "Un participant nommé « {name} » existe déjà",
    },
    # --- Participants ---
    "只有个人赛接受报名": {
        "en": "Only individual tournaments accept registrations",
        "fr": "Seuls les tournois individuels acceptent les inscriptions",
    },
    "赛事已结算，参赛名单已锁定": {
        "en": "The tournament is settled, the entry list is locked",
        "fr": "Le tournoi est réglé, la liste des participants est verrouillée",
    },
    "赛事已结算": {
        "en": "The tournament is already settled",
        "fr": "Le tournoi est déjà réglé",
    },
    "比赛日期已过，无法报名": {
        "en": "The tournament date has passed, registration is closed",
        "fr": "La date du tournoi est passée, les inscriptions sont closes",
    },
    "比赛已开始，无法加入": {
        "en": "The tournament has already started, you can no longer join",
        "fr": "Le tournoi a déjà commencé, vous ne pouvez plus vous inscrire",
    },
    "你已报名本比赛": {
        "en": "You are already registered for this tournament",
        "fr": "Vous êtes déjà inscrit à ce tournoi",
    },
    "赛事已结算，无法退出": {
        "en": "The tournament is settled, you can no longer withdraw",
        "fr": "Le tournoi est réglé, vous ne pouvez plus vous retirer",
    },
    "比赛已开始，无法退出": {
        "en": "The tournament has already started, you can no longer withdraw",
        "fr": "Le tournoi a déjà commencé, vous ne pouvez plus vous retirer",
    },
    "你尚未参加此赛事": {
        "en": "You are not taking part in this tournament",
        "fr": "Vous ne participez pas à ce tournoi",
    },
    "该账号已参加本比赛": {
        "en": "This account is already taking part in this tournament",
        "fr": "Ce compte participe déjà à ce tournoi",
    },
    "没有找到该邮箱或名称对应的账号": {
        "en": "No account found for that email address or name",
        "fr": "Aucun compte ne correspond à cette adresse e-mail ou à ce nom",
    },
    "不能添加自己": {
        "en": "You cannot add yourself",
        "fr": "Vous ne pouvez pas vous ajouter vous-même",
    },
    "该账号未授权你直接将其加入比赛": {
        "en": "This account has not authorised you to add them directly",
        "fr": "Ce compte ne vous a pas autorisé à l'inscrire directement",
    },
    # --- Ratings and settlement ---
    # The seeded name of the built-in rating category. Unlike every other entry this is
    # not a message but a piece of data, translated on read only while it is still the
    # untouched seed (see `models.db.rating.display_rating_category_name`).
    "加华积分": {
        "en": "Jiahua Rating",
        "fr": "Cote Jiahua",
    },
    "找不到该积分类别": {
        "en": "Rating category not found",
        "fr": "Catégorie de classement introuvable",
    },
    "内置积分类别「{name}」不可删除": {
        "en": "The built-in rating category “{name}” cannot be deleted",
        "fr": "La catégorie de classement intégrée « {name} » ne peut pas être supprimée",
    },
    "该积分类别下已有结算赛事，无法删除": {
        "en": "This rating category already has settled tournaments and cannot be deleted",
        "fr": (
            "Cette catégorie de classement comporte déjà des tournois réglés "
            "et ne peut pas être supprimée"
        ),
    },
    "该积分类别仍被比赛或选手积分引用，无法删除": {
        "en": (
            "This rating category is still referenced by tournaments or player ratings "
            "and cannot be deleted"
        ),
        "fr": (
            "Cette catégorie de classement est encore référencée par des tournois ou des "
            "classements de joueurs et ne peut pas être supprimée"
        ),
    },
    "结算未能完成": {
        "en": "The settlement could not be completed",
        "fr": "Le règlement n'a pas pu être finalisé",
    },
    "本比赛不参与积分": {
        "en": "This tournament does not count towards a rating",
        "fr": "Ce tournoi ne compte pas pour un classement",
    },
    "已结算的赛事不能再修改初始积分": {
        "en": "Initial ratings can no longer be changed once the tournament is settled",
        "fr": "Les classements initiaux ne sont plus modifiables une fois le tournoi réglé",
    },
    "该队伍尚未绑定账号": {
        "en": "This team is not linked to an account yet",
        "fr": "Cette équipe n'est pas encore liée à un compte",
    },
    "该参赛人员尚未绑定账号": {
        "en": "This participant is not linked to an account yet",
        "fr": "Ce participant n'est pas encore lié à un compte",
    },
    "个人积分赛只能通过选择已注册账号来添加参赛者（报名申请或直接添加），不能手动输入队伍名称": {
        "en": (
            "Rated individual tournaments add participants by selecting a registered account "
            "(join request or direct add), not by typing a team name"
        ),
        "fr": (
            "Dans un tournoi individuel classé, les participants sont ajoutés en sélectionnant "
            "un compte enregistré (demande d'inscription ou ajout direct), et non en saisissant "
            "un nom d'équipe"
        ),
    },
    "个人积分赛只能通过选择已注册账号来添加参赛者（报名申请或直接添加），不能手动输入名称": {
        "en": (
            "Rated individual tournaments add participants by selecting a registered account "
            "(join request or direct add), not by typing a name"
        ),
        "fr": (
            "Dans un tournoi individuel classé, les participants sont ajoutés en sélectionnant "
            "un compte enregistré (demande d'inscription ou ajout direct), et non en saisissant "
            "un nom"
        ),
    },
    "该账号已有生效积分，不能再设置初始积分": {
        "en": "This account already has an active rating, an initial rating can no longer be set",
        "fr": (
            "Ce compte possède déjà un classement actif, il n'est plus possible de définir "
            "un classement initial"
        ),
    },
    "已提交，待管理员审核初始分并完成结算": {
        "en": "Submitted. An administrator will review the initial ratings and settle the results",
        "fr": (
            "Demande envoyée. Un administrateur examinera les classements initiaux et "
            "finalisera le règlement"
        ),
    },
    "初始积分仍在审核中，请先完成审核": {
        "en": "The initial ratings are still under review, complete the review first",
        "fr": "Les classements initiaux sont encore en cours d'examen, terminez-le d'abord",
    },
    "可以结算": {
        "en": "Ready to settle",
        "fr": "Prêt à être réglé",
    },
    "有 {count} 名选手的初始分待管理员审核": {
        "en": "{count} player(s) have an initial rating awaiting administrator review",
        "fr": "{count} joueur(s) ont un classement initial en attente de validation",
    },
    "本赛事已经结算过了": {
        "en": "This tournament has already been settled",
        "fr": "Ce tournoi a déjà été réglé",
    },
    "请先推进完所有阶段再结算": {
        "en": "Advance through every stage before settling",
        "fr": "Terminez toutes les étapes avant de procéder au règlement",
    },
    "还有 {count} 支队伍未绑定账号，无法结算": {
        "en": "{count} team(s) are not linked to an account, settlement is not possible",
        "fr": "{count} équipe(s) ne sont pas liées à un compte, le règlement est impossible",
    },
    "还有 {count} 位参赛人员未绑定账号，无法结算": {
        "en": "{count} participant(s) are not linked to an account, settlement is not possible",
        "fr": "{count} participant(s) ne sont pas liés à un compte, le règlement est impossible",
    },
    "仍有对阵没有录入结果": {
        "en": "Some matches still have no result recorded",
        "fr": "Certains matchs n'ont pas encore de résultat enregistré",
    },
    "还没有已完成的对阵可供结算": {
        "en": "There is no completed match to settle yet",
        "fr": "Aucun match terminé ne peut encore être réglé",
    },
    "有 {count} 名参赛者尚未设置初始积分，无法结算": {
        "en": "{count} participant(s) have no initial rating; set one before settling",
        "fr": (
            "{count} participant(s) n'ont pas de classement initial, définissez-en un "
            "avant le règlement"
        ),
    },
    # --- Matches, courts and rounds ---
    "赛事已结算，比分已冻结": {
        "en": "The tournament is settled, scores are frozen",
        "fr": "Le tournoi est réglé, les scores sont figés",
    },
    "乒乓球没有平局，请录入分出胜负的比分": {
        "en": "Table tennis has no draws, record a score with a winner",
        "fr": "Le tennis de table n'admet pas de match nul, saisissez un score avec un vainqueur",
    },
    "该场地已被 {count} 场对阵使用，无法删除": {
        "en": "This court is used by {count} match(es) and cannot be deleted",
        "fr": "Ce terrain est utilisé par {count} match(s) et ne peut pas être supprimé",
    },
    "阶段类型 {type} 不支持手动创建回合": {
        "en": "Stage type {type} does not support creating rounds manually",
        "fr": "Le type d'étape {type} ne permet pas de créer des tours manuellement",
    },
    "阶段类型 {type} 无法自动创建对阵": {
        "en": "Cannot automatically create matches for stage type {type}",
        "fr": "Impossible de créer automatiquement les matchs pour le type d'étape {type}",
    },
    "找不到 ID 为 {id} 的回合": {
        "en": "No round found with ID {id}",
        "fr": "Aucun tour trouvé avec l'identifiant {id}",
    },
    "找不到 ID 为 {id} 的对阵": {
        "en": "No match found with ID {id}",
        "fr": "Aucun match trouvé avec l'identifiant {id}",
    },
    "找不到 ID 为 {id} 的队伍": {
        "en": "No team found with ID {id}",
        "fr": "Aucune équipe trouvée avec l'identifiant {id}",
    },
    "找不到 ID 为 {id} 的参赛人员": {
        "en": "No participant found with ID {id}",
        "fr": "Aucun participant trouvé avec l'identifiant {id}",
    },
    # --- Stages and stage items ---
    "找不到 ID 为 {id} 的阶段": {
        "en": "No stage found with ID {id}",
        "fr": "Aucune étape trouvée avec l'identifiant {id}",
    },
    "找不到 ID 为 {id} 的阶段项目": {
        "en": "No stage item found with ID {id}",
        "fr": "Aucun élément d'étape trouvé avec l'identifiant {id}",
    },
    "找不到该阶段项目的输入位": {
        "en": "Stage item input slot not found",
        "fr": "Emplacement d'entrée de l'élément d'étape introuvable",
    },
    "找不到对应的阶段": {
        "en": "The matching stage could not be found",
        "fr": "L'étape correspondante est introuvable",
    },
    "阶段项目不存在": {
        "en": "This stage item does not exist",
        "fr": "Cet élément d'étape n'existe pas",
    },
    "该阶段还有阶段项目，请先删除": {
        "en": "This stage still has stage items, delete them first",
        "fr": "Cette étape comporte encore des éléments, supprimez-les d'abord",
    },
    "该阶段处于激活状态，请先激活其他阶段": {
        "en": "This stage is active, activate another stage first",
        "fr": "Cette étape est active, activez d'abord une autre étape",
    },
    "没有下一个阶段": {
        "en": "There is no next stage",
        "fr": "Il n'y a pas d'étape suivante",
    },
    "没有上一个阶段": {
        "en": "There is no previous stage",
        "fr": "Il n'y a pas d'étape précédente",
    },
    "还无法确定下一阶段的队伍。请确保之前的每个阶段项目都已分配队伍并已结束。": {
        "en": (
            "The teams of the next stage cannot be determined yet. Make sure every earlier "
            "stage item has its teams assigned and has finished."
        ),
        "fr": (
            "Les équipes de l'étape suivante ne peuvent pas encore être déterminées. "
            "Assurez-vous que chaque élément d'étape précédent a ses équipes affectées "
            "et est terminé."
        ),
    },
    "还无法确定下一阶段的参赛人员。请确保之前的每个阶段项目都已分配参赛人员并已结束。": {
        "en": (
            "The participants of the next stage cannot be determined yet. Make sure every "
            "earlier stage item has its participants assigned and has finished."
        ),
        "fr": (
            "Les participants de l'étape suivante ne peuvent pas encore être déterminés. "
            "Assurez-vous que chaque élément d'étape précédent a ses participants affectés "
            "et est terminé."
        ),
    },
    "有 {count} 名选手尚未配置初始/正式积分，无法开始比赛": {
        "en": (
            "{count} player(s) have no initial or official rating yet, so the tournament "
            "cannot start"
        ),
        "fr": (
            "{count} joueur(s) n'ont pas encore de classement initial ou officiel, "
            "le tournoi ne peut pas commencer"
        ),
    },
    # --- Scheduling ---
    "队伍数量无效，应为 {options} 之一": {
        "en": "Invalid number of teams, it must be one of {options}",
        "fr": "Nombre d'équipes invalide, il doit être l'un des suivants : {options}",
    },
    "参赛人员数量无效，应为 {options} 之一": {
        "en": "Invalid number of participants, it must be one of {options}",
        "fr": "Nombre de participants invalide, il doit être l'un des suivants : {options}",
    },
    "小组数量至少为 1": {
        "en": "There must be at least 1 group",
        "fr": "Il faut au moins 1 groupe",
    },
    "{team_count} 支队伍无法分成 {group_count} 个每组至少 2 队的小组": {
        "en": "{team_count} teams cannot be split into {group_count} groups of at least 2 teams",
        "fr": (
            "{team_count} équipes ne peuvent pas être réparties en {group_count} groupes "
            "d'au moins 2 équipes"
        ),
    },
    "{team_count} 位参赛人员无法分成 {group_count} 个每组至少 2 人的小组": {
        "en": (
            "{team_count} participants cannot be split into {group_count} groups of at least "
            "2 participants"
        ),
        "fr": (
            "{team_count} participants ne peuvent pas être répartis en {group_count} groupes "
            "d'au moins 2 participants"
        ),
    },
    "淘汰赛至少需要选择 2 个晋级名额": {
        "en": "A single elimination bracket needs at least 2 qualifying places",
        "fr": "Un tableau à élimination directe requiert au moins 2 places qualificatives",
    },
    "单个对阵表的晋级人数过多（最多 64 人）": {
        "en": "Too many qualifiers for a single bracket (64 at most)",
        "fr": "Trop de qualifiés pour un seul tableau (64 au maximum)",
    },
    # --- Subscriptions and generic validation ---
    "当前套餐（{account_type}）最多允许 {constraint} 个{attribute}": {
        "en": "Your current plan ({account_type}) allows at most {constraint} {attribute}",
        "fr": "Votre offre actuelle ({account_type}) autorise au maximum {constraint} {attribute}",
    },
    "找不到 ID 为 {value} 的{name}": {
        "en": "No {name} found with ID {value}",
        # `{name}` comes with its French article (see ENTITY_NOUNS), so the sentence stays
        # grammatical whatever the gender of the entity.
        "fr": "Impossible de trouver {name} avec l'identifiant {value}",
    },
    # --- Entity nouns interpolated into the message above (bracket/sql/validation.py) ---
    "队伍": {"en": "team", "fr": "l'équipe"},
    "参赛人员": {"en": "participant", "fr": "le participant"},
    "场地": {"en": "court", "fr": "le terrain"},
    "阶段": {"en": "stage", "fr": "l'étape"},
    "阶段项目": {"en": "stage item", "fr": "l'élément d'étape"},
    "阶段项目输入位": {"en": "stage item input", "fr": "l'entrée de l'élément d'étape"},
    "回合": {"en": "round", "fr": "le tour"},
    "对阵": {"en": "match", "fr": "le match"},
    "队伍成员": {"en": "player", "fr": "le joueur"},
    "成员": {"en": "member", "fr": "le membre"},
}

# Message id -> the id to use when the request addresses an individual tournament, where a
# "team" is a single person and reads 参赛人员 (participant). Both ids are translated in the
# catalog above; `tr` swaps the id before translating, so every language follows along.
INDIVIDUAL_MESSAGES: dict[str, str] = {
    "该队伍已被分配到其他阶段项目": "该参赛人员已被分配到其他阶段项目",
    "该队伍已绑定其他账号": "该参赛人员已绑定其他账号",
    "该账号在本比赛中已有队伍": "该账号已参加本比赛",
    "该队伍仍关联着比赛对阵": "该参赛人员仍关联着比赛对阵",
    "该队伍不能作为此阶段项目的输入": "该参赛人员不能作为此阶段项目的输入",
    "该比赛还有队伍，请先删除队伍": "该比赛还有参赛人员，请先删除参赛人员",
    "队伍名“{name}”已存在": "参赛人员“{name}”已存在",
    "该队伍尚未绑定账号": "该参赛人员尚未绑定账号",
    "个人积分赛只能通过选择已注册账号来添加参赛者（报名申请或直接添加），不能手动输入队伍名称": (
        "个人积分赛只能通过选择已注册账号来添加参赛者（报名申请或直接添加），不能手动输入名称"
    ),
    "还有 {count} 支队伍未绑定账号，无法结算": "还有 {count} 位参赛人员未绑定账号，无法结算",
    "找不到 ID 为 {id} 的队伍": "找不到 ID 为 {id} 的参赛人员",
    "还无法确定下一阶段的队伍。请确保之前的每个阶段项目都已分配队伍并已结束。": (
        "还无法确定下一阶段的参赛人员。请确保之前的每个阶段项目都已分配参赛人员并已结束。"
    ),
    "队伍数量无效，应为 {options} 之一": "参赛人员数量无效，应为 {options} 之一",
    "{team_count} 支队伍无法分成 {group_count} 个每组至少 2 队的小组": (
        "{team_count} 位参赛人员无法分成 {group_count} 个每组至少 2 人的小组"
    ),
    # Entity nouns interpolated into "找不到 ID 为 {value} 的{name}".
    "队伍": "参赛人员",
    "队伍成员": "成员",
}

# Entity class name (a `*Id` type from `utils.id_types` without its `Id` suffix) -> the
# Chinese noun that acts as its message id above.
#
# This lives here rather than next to the `*Id` NewTypes because those are bare, string-free
# type aliases; keeping the nouns in the catalog keeps every user-facing string in one file.
ENTITY_NOUNS: dict[str, str] = {
    "Team": "队伍",
    "Court": "场地",
    "Stage": "阶段",
    "StageItem": "阶段项目",
    "StageItemInput": "阶段项目输入位",
    "Round": "回合",
    "Match": "对阵",
    "Player": "队伍成员",
}

# The name the built-in rating category is seeded with at DB init. It is a message id in
# the catalog above; `models.db.rating` compares the stored name against it to tell an
# untouched seed (translatable) from a name an admin chose (never translated).
SEEDED_RATING_CATEGORY_NAME = "加华积分"


def tr(message: str) -> str:
    """Translate a message id into the language of the current request.

    Requests about an individual tournament first swap the id for its participant-worded
    counterpart, so the wording follows the tournament in every language.

    Returns `message` unchanged for `zh` and whenever the catalog has no entry, so an
    untranslated string never raises — it just stays Chinese.
    """
    if get_individual_wording():
        message = INDIVIDUAL_MESSAGES.get(message, message)

    language = get_language()
    if language == DEFAULT_LANGUAGE:
        return message

    return TRANSLATIONS.get(message, {}).get(language, message)


def tr_entity(entity_name: str) -> str:
    """Translate the noun of an entity, e.g. the `Team` of a `TeamId`.

    An unmapped class name falls back to itself, so a new `*Id` type shows up untranslated
    instead of raising in the middle of an error response.
    """
    return tr(ENTITY_NOUNS.get(entity_name, entity_name))
