#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <string>
#include <vector>

namespace {

bool sequence_to_strings(PyObject* seq_obj, std::vector<std::string>& out) {
    PyObject* seq = PySequence_Fast(seq_obj, "expected a sequence of strings");
    if (seq == nullptr) {
        return false;
    }

    Py_ssize_t size = PySequence_Fast_GET_SIZE(seq);
    PyObject** items = PySequence_Fast_ITEMS(seq);
    out.reserve(static_cast<size_t>(size));

    for (Py_ssize_t i = 0; i < size; ++i) {
        PyObject* item = items[i];
        if (!PyUnicode_Check(item)) {
            Py_DECREF(seq);
            PyErr_SetString(PyExc_TypeError, "sequence items must be strings");
            return false;
        }
        Py_ssize_t item_size = 0;
        const char* data = PyUnicode_AsUTF8AndSize(item, &item_size);
        if (data == nullptr) {
            Py_DECREF(seq);
            return false;
        }
        out.emplace_back(data, static_cast<size_t>(item_size));
    }

    Py_DECREF(seq);
    return true;
}

PyObject* py_contains_any(PyObject* /*self*/, PyObject* args) {
    PyObject* text_obj = nullptr;
    PyObject* patterns_obj = nullptr;
    if (!PyArg_ParseTuple(args, "OO:contains_any", &text_obj, &patterns_obj)) {
        return nullptr;
    }

    if (!PyUnicode_Check(text_obj)) {
        PyErr_SetString(PyExc_TypeError, "text must be a string");
        return nullptr;
    }

    Py_ssize_t text_size = 0;
    const char* text_data = PyUnicode_AsUTF8AndSize(text_obj, &text_size);
    if (text_data == nullptr) {
        return nullptr;
    }
    std::string text(text_data, static_cast<size_t>(text_size));

    std::vector<std::string> patterns;
    if (!sequence_to_strings(patterns_obj, patterns)) {
        return nullptr;
    }

    for (const auto& pattern : patterns) {
        if (!pattern.empty() && text.find(pattern) != std::string::npos) {
            Py_RETURN_TRUE;
        }
    }
    Py_RETURN_FALSE;
}

PyObject* py_prefix_matches(PyObject* /*self*/, PyObject* args) {
    PyObject* prefix_obj = nullptr;
    PyObject* options_obj = nullptr;
    if (!PyArg_ParseTuple(args, "OO:prefix_matches", &prefix_obj, &options_obj)) {
        return nullptr;
    }

    if (!PyUnicode_Check(prefix_obj)) {
        PyErr_SetString(PyExc_TypeError, "prefix must be a string");
        return nullptr;
    }

    Py_ssize_t prefix_size = 0;
    const char* prefix_data = PyUnicode_AsUTF8AndSize(prefix_obj, &prefix_size);
    if (prefix_data == nullptr) {
        return nullptr;
    }
    std::string prefix(prefix_data, static_cast<size_t>(prefix_size));

    std::vector<std::string> options;
    if (!sequence_to_strings(options_obj, options)) {
        return nullptr;
    }

    PyObject* result = PyList_New(0);
    if (result == nullptr) {
        return nullptr;
    }

    for (const auto& option : options) {
        if (option.rfind(prefix, 0) == 0) {
            PyObject* py_value = PyUnicode_FromStringAndSize(
                option.data(),
                static_cast<Py_ssize_t>(option.size())
            );
            if (py_value == nullptr) {
                Py_DECREF(result);
                return nullptr;
            }
            if (PyList_Append(result, py_value) != 0) {
                Py_DECREF(py_value);
                Py_DECREF(result);
                return nullptr;
            }
            Py_DECREF(py_value);
        }
    }

    return result;
}

PyMethodDef FASTCORE_METHODS[] = {
    {
        "contains_any",
        py_contains_any,
        METH_VARARGS,
        "Return True if text contains any pattern."
    },
    {
        "prefix_matches",
        py_prefix_matches,
        METH_VARARGS,
        "Return options that start with prefix."
    },
    {nullptr, nullptr, 0, nullptr},
};

PyModuleDef FASTCORE_MODULE = {
    PyModuleDef_HEAD_INIT,
    "_fastcore",
    "Native fast paths for NoNail.",
    -1,
    FASTCORE_METHODS,
};

}  // namespace

PyMODINIT_FUNC PyInit__fastcore(void) {
    return PyModule_Create(&FASTCORE_MODULE);
}
