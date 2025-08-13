import multiprocessing
import random
import time
import prettytable
from typing import TypeVar, List, Tuple, Type, Protocol
from multiprocessing.managers import SyncManager, DictProxy, ValueProxy
from multiprocessing.synchronize import Lock
from queue import Empty
import os

T = TypeVar("T")
K = TypeVar("K", int, float)


class SynchronizedValue(Protocol[K]):
    value: K


def create_object(filename: str, obj_class: Type[T], manager: SyncManager) -> List[T]:
    objects: List[T] = []
    with open(filename, "r", encoding="UTF-8") as file:
        for line in file:
            parts: List[str] = line.strip().split()
            objects.append(obj_class(parts[0], parts[1], manager))
    return objects


def create_questions() -> List["Question"]:
    questions: List[Question] = []
    with open("questions.txt", "r", encoding="UTF-8") as file:
        for lines in file:
            parts: List[str] = lines.strip(" ").split()
            questions.append(Question(parts))
    return questions


class Question:
    def __init__(self, list_words: List[str]):
        self.__list_words: List[str] = list_words
        self.__total_correct_answers: SynchronizedValue[int] = multiprocessing.Value(
            "i", 0
        )

    def get_words(self) -> List[str]:
        return self.__list_words

    def get_total_correct_answers(self):
        return self.__total_correct_answers.value

    def add_correct_answer(self) -> None:
        self.__total_correct_answers.value += 1


class Student:
    def __init__(self, name: str, gender: str, manager: SyncManager):
        self.name: str = name
        self.status: DictProxy[str, str] = manager.dict({"status": "Очередь"})
        self.gender: str = gender
        self.__passed_time: ValueProxy[float] = manager.Value("d", -1.0)

    def set_status(self, status: str) -> None:
        self.status["status"] = status
        if self.status["status"] != "Очередь":
            self.__passed_time.value = time.time()

    def get_passed_time(self) -> float:
        return self.__passed_time.value

    def get_answer_question(self, words: List[str]) -> str:
        number_of_words: int = len(words)
        probabilities: List[float] = get_probability_golden_ratio(number_of_words)

        if self.gender == "Ж":
            probabilities = probabilities[::-1]

        chosen_word: str = random.choices(words, weights=probabilities, k=1)[0]

        return chosen_word


class Examiner:
    def __init__(self, name: str, gender: str, manager: SyncManager):
        self.name: str = name
        self.gender: str = gender
        self.current_student_name: DictProxy[str, str] = manager.dict(
            {"student_name": "-"}
        )
        self.mood: str = random.choices(
            ["Хорошее", "Плохое", "Нейтральное"], weights=[1 / 4, 1 / 8, 5 / 8], k=1
        )[0]
        self.__number_of_students: SynchronizedValue[int] = multiprocessing.Value(
            "i", 0
        )
        self.__failed_student: SynchronizedValue[int] = multiprocessing.Value("i", 0)
        self.exam_duration: float = random.uniform(len(name) - 1, len(name) + 1)
        self.__total_time_work: SynchronizedValue[float] = multiprocessing.Value(
            "d", 0.0
        )
        self.__work_start_time: SynchronizedValue[float] = multiprocessing.Value(
            "d", 0.0
        )
        self.lock: Lock = multiprocessing.Lock()

    def set_total_time_work(self) -> None:
        with self.lock:
            if not self.__work_start_time.value == 0.0:
                self.__total_time_work.value += (
                    time.time() - self.__work_start_time.value
                )
                self.__work_start_time.value = 0.0

    def set_current_student_name(self, student_name: str) -> None:
        self.current_student_name["student_name"] = student_name

    def add_failed_student(self) -> None:
        self.__failed_student.value += 1

    def add_number_of_student(self) -> None:
        self.__number_of_students.value += 1

    def resume_work_start_time(self):
        with self.lock:
            # Начать отсчёт активного времени
            if self.__work_start_time.value == 0.0:
                self.__work_start_time.value = time.time()

    def get_number_of_student(self) -> int:
        return self.__number_of_students.value

    def get_failed_student(self) -> int:
        return self.__failed_student.value

    def get_total_time_work(self):
        with self.lock:
            if not self.__work_start_time.value == 0.0:
                # Экзаменатор сейчас работает: накопленное + текущее активное время
                return self.__total_time_work.value + (
                    time.time() - self.__work_start_time.value
                )
            else:
                # Экзаменатор на паузе: только накопленное время
                return self.__total_time_work.value

    def get_percent_failed_students(self) -> float:
        try:
            return self.__failed_student.value * 100 / self.__number_of_students.value
        except ZeroDivisionError:
            return 0.0

    def get_answer_question(self, words: List[str]) -> List[str]:
        available_words: List[str] = words.copy()
        number_of_words: int = len(available_words)
        chosen_words: List[str] = []
        probabilities: List[float] = get_probability_golden_ratio(number_of_words)

        if self.gender == "Ж":
            probabilities = probabilities[::-1]
        while available_words:
            chosen_word = random.choices(available_words, weights=probabilities, k=1)[0]
            chosen_words.append(chosen_word)
            idx = available_words.index(chosen_word)
            del available_words[idx]
            del probabilities[idx]
            if not random.choices([True, False], weights=[1 / 3, 2 / 3], k=1)[0]:
                break

        return chosen_words

    def evaluate_answers(
        self, bank_of_questions: List[Question], student: Student
    ) -> Tuple[int, int]:

        questions: List[Question] = random.sample(bank_of_questions, 3)
        correct_answers = 0
        wrong_answers = 0
        for question in questions:
            question_word: List[str] = question.get_words()
            student_answer: str = student.get_answer_question(question_word)
            examiner_answer: List[str] = self.get_answer_question(question_word)

            if student_answer in examiner_answer:
                correct_answers += 1
                question.add_correct_answer()
            else:
                wrong_answers += 1
        return correct_answers, wrong_answers

    def conduct_exam(self, student: Student, bank_of_questions: List[Question]):
        self.resume_work_start_time()
        self.set_current_student_name(student.name)
        self.add_number_of_student()

        correct_answers, wrong_answers = self.evaluate_answers(
            bank_of_questions, student
        )

        time.sleep(self.exam_duration)
        if self.mood == "Хорошее":
            student.set_status("Сдал")
        elif self.mood == "Плохое":
            student.set_status("Провалил")
            self.add_failed_student()
        elif self.mood == "Нейтральное":
            if correct_answers > wrong_answers:
                student.set_status("Сдал")
            else:
                student.set_status("Провалил")
                self.add_failed_student()
        self.set_total_time_work()


def exam_process(
    examiner: Examiner,
    bank_of_questions: List[Question],
    queue_of_students: multiprocessing.Queue,
    time_start_exam: float,
) -> None:
    while True:
        try:
            if check_lunch(time_start_exam):
                time.sleep(random.uniform(12, 18))
                time_start_exam = time.time()
            student: Student = queue_of_students.get(timeout=1)
            examiner.conduct_exam(student, bank_of_questions)
            examiner.set_current_student_name("-")
        except Empty:
            break


def check_lunch(time_start_exam: float) -> bool:
    now = time.time()
    if now - time_start_exam > 30:
        if random.random() < 1 / 3:
            return True
    return False


def get_probability_golden_ratio(number_of_words: int) -> List[float]:
    phi = 1.618
    probabilities = []
    sum_prob = 0.0
    for i in range(number_of_words - 1):
        if i == 0:
            prob = 1 / phi
        else:
            prob = (1 - sum_prob) / phi
        probabilities.append(prob)
        sum_prob += prob
    probabilities.append(1 - sum_prob)
    return probabilities


def choose_better_student(students: List[Student]) -> Tuple[str, ...]:
    succeeded_students: List[Student] = [
        s for s in students if s.status["status"] == "Сдал"
    ]
    if not succeeded_students:
        return tuple()
    best_time: float = min(s.get_passed_time() for s in succeeded_students)
    better_student: Tuple[str, ...] = tuple(
        s.name for s in succeeded_students if s.get_passed_time() == best_time
    )

    return better_student


def choose_worst_student(students: List[Student]) -> Tuple[str, ...]:
    failed_students: List[Student] = [
        s for s in students if s.status["status"] == "Провалил"
    ]
    if not failed_students:
        return tuple()
    better_time: float = min(s.get_passed_time() for s in failed_students)
    worst_student: Tuple[str, ...] = tuple(
        s.name for s in failed_students if s.get_passed_time() == better_time
    )
    return worst_student


def choose_better_examiner(examiners: List[Examiner]) -> Tuple[str, ...]:
    best_percent_failed_student: float = min(
        x.get_percent_failed_students() for x in examiners
    )
    better_examiner: Tuple[str, ...] = tuple(
        x.name
        for x in examiners
        if x.get_percent_failed_students() == best_percent_failed_student
    )
    return better_examiner


def choose_better_questions(questions: List[Question]) -> Tuple[str, ...]:
    max_correct_answers: int = max(q.get_total_correct_answers() for q in questions)
    better_question: List[List[str]] = [
        q.get_words()
        for q in questions
        if q.get_total_correct_answers() == max_correct_answers
    ]
    return tuple(" ".join(q) for q in better_question)


def build_students_table(
    queue_of_students: List[Student],
) -> Tuple[prettytable.PrettyTable, int]:
    table_student: prettytable.PrettyTable = prettytable.PrettyTable()
    table_student.field_names = ["Студент", "Статус"]
    status_priority = {"Очередь": 0, "Сдал": 1, "Провалил": 2}
    sorted_queue_of_students: List[Student] = sorted(
        queue_of_students,
        key=lambda student: status_priority.get(student.status["status"], 3),
    )
    for person in sorted_queue_of_students:
        table_student.add_row([person.name, person.status["status"]])
    return table_student, sum(
        1 for s in queue_of_students if s.status["status"] == "Очередь"
    )


def build_examiners_table(
    examiners: List[Examiner], exam_is_finished: bool
) -> prettytable.PrettyTable:
    table_examiner: prettytable.PrettyTable = prettytable.PrettyTable()
    if not exam_is_finished:
        table_examiner.field_names = [
            "Экзаменатор",
            "Текущий студент",
            "Всего студентов",
            "Завалил",
            "Время работы",
        ]
    else:
        table_examiner.field_names = [
            "Экзаменатор",
            "Всего студентов",
            "Завалил",
            "Время работы",
        ]
    for examiner in examiners:
        total_time = examiner.get_total_time_work()
        row = [examiner.name]
        if not exam_is_finished:
            row.append(examiner.current_student_name["student_name"])
        row.extend(
            [
                str(examiner.get_number_of_student()),
                str(examiner.get_failed_student()),
                f"{total_time:.2f}",
            ]
        )
        table_examiner.add_row(row)
    return table_examiner


def check_exam_success(students: List[Student]) -> str:
    total_students: int = len(students)
    succeeded_students: int = len([s for s in students if s.status["status"] == "Сдал"])
    percent_succeed_student: float = succeeded_students * 100 / total_students
    result_exam: str = "Экзамен не удался"
    if percent_succeed_student > 85:
        result_exam = "Экзамен удался"
    return result_exam


def monitoring(
    students: List[Student],
    examiners: List[Examiner],
    time_start_exam: float,
    bank_questions: List[Question],
) -> None:
    exam_is_finished: bool = False
    while any([s.status["status"] == "Очередь" for s in students]):
        print_table(
            students, examiners, exam_is_finished, time_start_exam, bank_questions
        )
        time.sleep(0.3)
    exam_is_finished = True
    print_table(students, examiners, exam_is_finished, time_start_exam, bank_questions)


def print_table(
    queue_of_students: List[Student],
    examiners: List[Examiner],
    exam_is_finished: bool,
    time_start_exam: float,
    bank_questions: List[Question],
):
    students_table, number_of_students_in_queue = build_students_table(
        queue_of_students
    )
    examiners_table = build_examiners_table(examiners, exam_is_finished)
    clear_screen()
    print(students_table)
    print(examiners_table)
    if not exam_is_finished:
        print(
            f"Осталось в очереди {number_of_students_in_queue} из {len(queue_of_students)}"
        )
        print(f"Время с момента начала экзамена {time.time() - time_start_exam:.2f}")
    else:
        better_student: Tuple[str, ...] = choose_better_student(queue_of_students)
        better_examiner: Tuple[str, ...] = choose_better_examiner(examiners)
        worst_student: Tuple[str, ...] = choose_worst_student(queue_of_students)
        better_question: Tuple[str, ...] = choose_better_questions(bank_questions)
        final_result: str = check_exam_success(queue_of_students)
        print(
            f"Время с момента начала экзамена и до момента и его завершения: {time.time() - time_start_exam:.2f}"
        )
        print(f"Имена лучших студентов: {', '.join(better_student)}")
        print(f"Имена лучших экзаменаторов: {', '.join(better_examiner)}")
        print(
            f"Имена студентов, которых после экзамена отчислят: {', '.join(worst_student)}"
        )
        print(f"Лучшие вопросы: {', '.join(better_question)}")
        print(f"Вывод: {final_result}")


def clear_screen() -> None:
    # Отчищает командную строку
    if "TERM" not in os.environ:
        os.environ["TERM"] = "xterm"
    os.system("cls" if os.name == "nt" else "clear")


def main() -> None:
    manager: SyncManager = multiprocessing.Manager()
    students: List[Student] = create_object("students.txt", Student, manager)
    examiners: List[Examiner] = create_object("examiners.txt", Examiner, manager)
    bank_questions: List[Question] = create_questions()
    time_start_exam: float = time.time()

    queue_students: multiprocessing.Queue = multiprocessing.Queue()

    for student in students:
        queue_students.put(student)

    processes: List[multiprocessing.Process] = []
    for examiner in examiners:
        process: multiprocessing.Process = multiprocessing.Process(
            target=exam_process,
            args=(examiner, bank_questions, queue_students, time_start_exam),
            name=examiner.name,
        )
        processes.append(process)
        process.start()

    monitor_process = multiprocessing.Process(
        target=monitoring, args=(students, examiners, time_start_exam, bank_questions)
    )
    monitor_process.start()

    for p in processes:
        p.join()

    monitor_process.join()

    time.sleep(0.5)  # чтобы убедиться, что все процессы завершены


if __name__ == "__main__":
    main()
