!> Example Fortran module for testing documentation parsing
!> This module demonstrates various Fortran constructs
module example_module
    implicit none
    private
    
    public :: vector_type, add_vectors, normalize_vector
    
    !> A simple 3D vector type
    type :: vector_type
        real :: x = 0.0  !> X component
        real :: y = 0.0  !> Y component  
        real :: z = 0.0  !> Z component
    contains
        procedure :: magnitude => vector_magnitude
        procedure :: dot => vector_dot_product
    end type vector_type
    
contains

    !> Add two vectors together
    !> @param vec1 First vector
    !> @param vec2 Second vector  
    !> @return Resultant vector
    pure function add_vectors(vec1, vec2) result(result_vec)
        type(vector_type), intent(in) :: vec1, vec2
        type(vector_type) :: result_vec
        
        result_vec%x = vec1%x + vec2%x
        result_vec%y = vec1%y + vec2%y
        result_vec%z = vec1%z + vec2%z
    end function add_vectors
    
    !> Normalize a vector to unit length
    !> @param vec Vector to normalize
    subroutine normalize_vector(vec)
        type(vector_type), intent(inout) :: vec
        real :: mag
        
        mag = vec%magnitude()
        if (mag > 0.0) then
            vec%x = vec%x / mag
            vec%y = vec%y / mag
            vec%z = vec%z / mag
        end if
    end subroutine normalize_vector
    
    !> Calculate vector magnitude
    !> @param this Vector instance
    !> @return Magnitude of the vector
    pure function vector_magnitude(this) result(mag)
        class(vector_type), intent(in) :: this
        real :: mag
        
        mag = sqrt(this%x**2 + this%y**2 + this%z**2)
    end function vector_magnitude
    
    !> Calculate dot product of two vectors
    !> @param this First vector
    !> @param other Second vector
    !> @return Dot product result
    pure function vector_dot_product(this, other) result(dot_prod)
        class(vector_type), intent(in) :: this
        type(vector_type), intent(in) :: other
        real :: dot_prod
        
        dot_prod = this%x * other%x + this%y * other%y + this%z * other%z
    end function vector_dot_product

end module example_module