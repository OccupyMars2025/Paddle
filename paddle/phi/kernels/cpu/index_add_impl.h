// Copyright (c) 2022 PaddlePaddle Authors. All Rights Reserved.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#pragma once

#include "paddle/phi/common/int_array.h"
#include "paddle/phi/core/dense_tensor.h"
#include "paddle/phi/kernels/copy_kernel.h"
#include "paddle/phi/kernels/funcs/blas/blas.h"
#include "paddle/phi/kernels/funcs/eigen/common.h"
#include "paddle/phi/kernels/funcs/math_function.h"

namespace phi {
// template <typename Context, typename T, typename IndexT = int>
template <typename Context, typename T>
void IndexAddCPUImpl(const Context& ctx,
                  //  const DenseTensor& index,
                   const IntArray& index,
                   DenseTensor* output,
                   int axis,
                   T add_val) {
  auto output_dim = output->dims();
  auto output_dim_size = output_dim.size();
  // auto index_size = index.dims()[0];
  auto index_size = index.size();

  // DenseTensor index_cpu_copy;
  // if (!paddle::platform::is_cpu_place(index.place())) {
  //   phi::Copy(ctx, index, phi::CPUPlace(), true, &index_cpu_copy);
  // }
  // const IndexT* index_data = paddle::platform::is_cpu_place(index.place())
  //                                ? index.data<IndexT>()
  //                                : index_cpu_copy.data<IndexT>();
  const auto& index_data = index.GetData();

  auto slice_size = 1;
  for (auto i = axis + 1; i < output_dim_size; i++) {
    slice_size *= output_dim[i];
  }

  auto outer_nums = 1;
  for (auto i = 0; i < axis; i++) {
    outer_nums *= output_dim[i];
  }

  for (size_t i = 0; i < index_size; i++) {
    PADDLE_ENFORCE_GE(
        index_data[i],
        0,
        phi::errors::InvalidArgument(
            "(elements of index of OP(index_add)) "
            "expected >= 0 and < %ld, but got %ld. Please check index "
            "value.",
            output_dim[axis],
            index_data[i]));
    PADDLE_ENFORCE_LT(
        index_data[i],
        output_dim[axis],
        phi::errors::InvalidArgument(
            "(elements of index of OP(index_add) "
            "expected >= 0 and < %ld, but got %ld. Please check index "
            "value.",
            output_dim[axis],
            index_data[i]));
  }

  output->Resize(phi::make_ddim({outer_nums, output_dim[axis], slice_size}));

  auto output_tensor = EigenTensor<T, 3>::From(*output);
  auto& place = *ctx.eigen_device();
  for (size_t j = 0; j < index_size; j++) {
    auto index_value = index_data[j];
    auto output_t = output_tensor.chip(index_value, 1);
    // output_t.device(place) = output_t.constant(fill_val);
    output_t.device(place) += output_t.constant(add_val);
  }
  output->Resize(output_dim);
}

}  // namespace phi